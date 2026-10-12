"""Persistencia de corridas (cada análisis completo).

- Con DATABASE_URL (nube): tabla `corridas`; las tablas van como listas de filas (orient='records') con la
  columna del índice incluida: ranking -> 'ticker', renta_fija -> 'ticker_iol', objetivos -> 'ticker'.
- Sin DATABASE_URL (desarrollo): reports/corridas/AAAAMMDD_HHMM/ con ranking.csv, renta_fija.csv,
  objetivos.csv, ordenes.csv, meta.json y guia.md. Pasar `base` fuerza archivos.
La web (y la app local) leen de acá: no recalculan nada para mostrar.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .config import CORRIDAS_DIR


@dataclass
class Corrida:
    stamp: str
    meta: dict
    ranking: pd.DataFrame
    renta_fija: pd.DataFrame = field(default_factory=pd.DataFrame)
    objetivos: pd.DataFrame = field(default_factory=pd.DataFrame)
    ordenes: pd.DataFrame = field(default_factory=pd.DataFrame)
    guia: str = ""
    dir: Path | None = None


def limpiar_json(o):
    """JSON (y jsonb) no admite NaN/inf, tipos de numpy/pandas, fechas sueltas ni el carácter NUL."""
    if isinstance(o, dict):
        return {str(k): limpiar_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [limpiar_json(v) for v in o]
    if o is None or o is pd.NaT or o is pd.NA:
        return None
    if hasattr(o, "tolist") and getattr(o, "ndim", 0) > 0:   # arrays de numpy
        return limpiar_json(o.tolist())
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.isoformat()
    if hasattr(o, "item") and not isinstance(o, (str, bytes)):
        o = o.item()
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, str):
        return o.replace("\x00", "")
    return o


_limpiar = limpiar_json   # nombre viejo

INDICES = {"ranking": "ticker", "renta_fija": "ticker_iol", "objetivos": "ticker"}
TEXTOS = ("alertas", "eventos", "nota", "senal", "tipo", "panel", "sector")


def _usa_db(base: Path | None) -> bool:
    from . import db
    return base is None and db.hay_db()


def modo_de(meta: dict) -> str:
    return "live" if str(meta.get("broker", "")).lower() in ("iol", "live") else "paper"


# ----------------------------------------------------------------------------- base de datos
def a_registros(df: pd.DataFrame | None, indice: str | None = None) -> list[dict]:
    if df is None or df.empty:
        return []
    if indice:
        df = df.reset_index(drop=True) if indice in df.columns else df.rename_axis(indice).reset_index()
    return limpiar_json(df.to_dict(orient="records"))


def de_registros(filas: list | None, indice: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame.from_records(filas or [])
    if indice and indice in df.columns:
        df = df.set_index(indice)
        df.index.name = indice if indice == "ticker_iol" else None
    return df


def _guardar_db(c: Corrida) -> None:
    from . import db
    db.guardar_corrida({
        "stamp": c.stamp, "modo": modo_de(c.meta), "meta": limpiar_json(c.meta),
        "ranking": a_registros(c.ranking, INDICES["ranking"]),
        "renta_fija": a_registros(c.renta_fija, INDICES["renta_fija"]),
        "objetivos": a_registros(c.objetivos, INDICES["objetivos"]),
        "ordenes": a_registros(c.ordenes), "guia": c.guia or "",
    })


def _textos(df: pd.DataFrame) -> pd.DataFrame:
    for col in TEXTOS:  # los textos vacíos vuelven como NaN/None
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
    return df


def _cargar_db(stamp: str) -> Corrida:
    from . import db
    f = db.cargar_corrida(stamp)
    if f is None:
        raise FileNotFoundError(f"No existe la corrida {stamp}")
    return Corrida(stamp=stamp, meta=f["meta"] or {},
                   ranking=_textos(de_registros(f["ranking"], INDICES["ranking"])),
                   renta_fija=de_registros(f["renta_fija"], INDICES["renta_fija"]),
                   objetivos=de_registros(f["objetivos"], INDICES["objetivos"]),
                   ordenes=de_registros(f["ordenes"]), guia=f["guia"] or "")


# ----------------------------------------------------------------------------- archivos
def _guardar_archivos(c: Corrida, base: Path | None) -> Path:
    d = (base or CORRIDAS_DIR) / c.stamp
    d.mkdir(parents=True, exist_ok=True)
    c.ranking.to_csv(d / "ranking.csv")
    for nombre, df in (("renta_fija", c.renta_fija), ("objetivos", c.objetivos)):
        if df is not None and not df.empty:
            df.to_csv(d / f"{nombre}.csv")
    if c.ordenes is not None and not c.ordenes.empty:
        c.ordenes.to_csv(d / "ordenes.csv", index=False)
    (d / "meta.json").write_text(json.dumps(limpiar_json(c.meta), ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "guia.md").write_text(c.guia, encoding="utf-8")
    return d


def _csv(p: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(p, **kw) if p.exists() else pd.DataFrame()


def _cargar_archivos(stamp: str, base: Path | None) -> Corrida:
    d = (base or CORRIDAS_DIR) / stamp
    return Corrida(
        stamp=stamp,
        meta=json.loads((d / "meta.json").read_text(encoding="utf-8")),
        ranking=_textos(_csv(d / "ranking.csv", index_col=0)),
        renta_fija=_csv(d / "renta_fija.csv", index_col=0),
        objetivos=_csv(d / "objetivos.csv", index_col=0),
        ordenes=_csv(d / "ordenes.csv"),
        guia=(d / "guia.md").read_text(encoding="utf-8") if (d / "guia.md").exists() else "",
        dir=d,
    )


# ----------------------------------------------------------------------------- interfaz
def guardar(c: Corrida, base: Path | None = None) -> Path | None:
    """Guarda la corrida. Devuelve la carpeta (archivos) o None (base de datos)."""
    if _usa_db(base):
        _guardar_db(c)
        c.dir = None
        return None
    c.dir = _guardar_archivos(c, base)
    return c.dir


def cargar(stamp: str, base: Path | None = None) -> Corrida:
    return _cargar_db(stamp) if _usa_db(base) else _cargar_archivos(stamp, base)


def listar(base: Path | None = None) -> list[str]:
    if _usa_db(base):
        from . import db
        return db.listar_corridas()
    d = base or CORRIDAS_DIR
    if not d.exists():
        return []
    return sorted((p.name for p in d.iterdir() if (p / "meta.json").exists()), reverse=True)


def ultima(base: Path | None = None) -> Corrida | None:
    stamps = listar(base)
    return cargar(stamps[0], base) if stamps else None
