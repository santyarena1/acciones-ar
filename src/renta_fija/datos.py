"""I/O de renta fija: términos (YAML), cotizaciones (data912), letras (argentinadatos), CER (BCRA) y feriados.

Todo lo descargado se guarda en data/cache/ con la fecha en el nombre (caché diaria): si existe el archivo del
día no se vuelve a pedir, y una fecha pasada sólo funciona si quedó su snapshot en caché.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests
import yaml

from ..config import CACHE_DIR, ROOT
from . import parsers

log = logging.getLogger(__name__)

RUTA_TERMINOS = ROOT / "config" / "renta_fija.yaml"
PANELES_DATA912 = ("arg_bonds", "arg_notes", "arg_corp")
DIAS_HISTORIA_CER = 60
HEADERS = {"Accept": "application/json", "User-Agent": "acciones-ar/renta-fija"}


def cargar_config(ruta: Path | None = None) -> dict[str, Any]:
    """YAML completo: {'parametros': {...}, 'instrumentos': {ticker: términos}}."""
    with open(ruta or RUTA_TERMINOS, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict) or "instrumentos" not in cfg:
        raise ValueError("renta_fija.yaml: falta la sección 'instrumentos'")
    cfg.setdefault("parametros", {})
    return cfg


def _ruta_cache(nombre: str, fecha: date) -> Path:
    return CACHE_DIR / f"rf_{nombre}_{fecha:%Y%m%d}.json"


def _get_json(url: str, timeout: float, params: dict[str, Any] | None = None) -> Any:
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _vencido(ruta: Path, ttl_min: float | None) -> bool:
    return ttl_min is not None and (time.time() - ruta.stat().st_mtime) > ttl_min * 60


def _cacheado(nombre: str, fecha: date, descargar: Callable[[], Any], refrescar: bool = False,
              ttl_min: float | None = None) -> Any:
    """Devuelve el JSON del día desde caché o lo descarga y lo guarda. Fechas pasadas: sólo caché.

    Con `ttl_min`, el caché de HOY se renueva si es más viejo (los precios cambian durante la rueda); si la
    descarga falla se usa el caché viejo con un aviso (mejor un precio de hace un rato que ninguno: el filtro de
    calidad y el control de precio en vivo del operador cubren el resto)."""
    ruta = _ruta_cache(nombre, fecha)
    hoy = fecha >= date.today()
    if ruta.exists() and not refrescar and not (hoy and _vencido(ruta, ttl_min)):
        return json.loads(ruta.read_text(encoding="utf-8"))
    if not hoy:
        raise FileNotFoundError(f"no hay snapshot en caché para {nombre} del {fecha} ({ruta.name})")
    try:
        datos = descargar()
    except (requests.RequestException, ValueError) as e:
        if ruta.exists():
            log.warning("No pude refrescar %s (%s): uso el caché de %s", nombre, e, ruta.name)
            return json.loads(ruta.read_text(encoding="utf-8"))
        raise
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ruta)
    return datos


def cotizaciones(fecha: date, fuentes: dict[str, str], timeout: float, refrescar: bool = False,
                 ttl_min: float | None = None) -> pd.DataFrame:
    """Cotizaciones de bonos, letras y ONs de data912 (una fila por símbolo, ARS, D=MEP y C=cable)."""
    base = fuentes.get("data912", "https://data912.com").rstrip("/")
    tablas = []
    for panel in PANELES_DATA912:
        try:
            raw = _cacheado(f"data912_{panel}", fecha, lambda p=panel: _get_json(f"{base}/live/{p}", timeout),
                            refrescar, ttl_min)
            tablas.append(parsers.parsear_data912(raw))
        except (requests.RequestException, ValueError, FileNotFoundError) as e:
            log.warning("No pude traer data912 %s: %s", panel, e)
    if not tablas:
        raise RuntimeError("Sin cotizaciones de renta fija (data912 no respondió y no hay caché)")
    df = pd.concat(tablas)
    return df[~df.index.duplicated(keep="first")]


def letras(fecha: date, fuentes: dict[str, str], timeout: float, refrescar: bool = False) -> pd.DataFrame:
    """Lecaps/Boncaps con TEA y vencimiento de argentinadatos (vacío si falla: es complementario)."""
    base = fuentes.get("argentinadatos", "https://api.argentinadatos.com").rstrip("/")
    try:
        raw = _cacheado("ad_letras", fecha, lambda: _get_json(f"{base}/v1/finanzas/letras", timeout), refrescar)
        return parsers.parsear_letras_argentinadatos(raw)
    except (requests.RequestException, ValueError, FileNotFoundError) as e:
        log.warning("No pude traer letras de argentinadatos: %s", e)
        return pd.DataFrame(columns=["ticker", "precio", "tea", "tem", "vencimiento", "dias", "volumen_efectivo_ars"])


def serie_cer(fecha: date, fuentes: dict[str, str], timeout: float, refrescar: bool = False) -> dict[date, float]:
    """CER diario de los últimos ~60 días (BCRA API v4.0, variable 30)."""
    url = fuentes.get("bcra_cer", "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/30")
    params = {"desde": (fecha - timedelta(days=DIAS_HISTORIA_CER)).isoformat(),
              "hasta": (fecha + timedelta(days=15)).isoformat()}
    try:
        raw = _cacheado("bcra_cer", fecha, lambda: _get_json(url, timeout, params), refrescar)
        return parsers.parsear_cer_bcra(raw)
    except (requests.RequestException, ValueError, FileNotFoundError) as e:
        log.warning("No pude traer el CER del BCRA (los bonos CER quedan sin TIR): %s", e)
        return {}


def feriados(anios: list[int], fuentes: dict[str, str], timeout: float) -> set[date]:
    """Feriados nacionales (argentinadatos). Se cachean por año; si falla, sólo se saltean fines de semana."""
    base = fuentes.get("argentinadatos", "https://api.argentinadatos.com").rstrip("/")
    out: set[date] = set()
    for anio in anios:
        ruta = CACHE_DIR / f"rf_feriados_{anio}.json"
        try:
            if ruta.exists():
                raw = json.loads(ruta.read_text(encoding="utf-8"))
            else:
                raw = _get_json(f"{base}/v1/feriados/{anio}", timeout)
                ruta.parent.mkdir(parents=True, exist_ok=True)
                ruta.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            out |= parsers.parsear_feriados(raw)
        except (requests.RequestException, ValueError, OSError) as e:
            log.warning("No pude traer feriados %s (sólo se excluyen fines de semana): %s", anio, e)
    return out
