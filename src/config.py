"""Carga de configuración del proyecto."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
REPORTS_DIR = ROOT / "reports"
CORRIDAS_DIR = REPORTS_DIR / "corridas"

USUARIO_PATH = DATA_DIR / "usuario.yaml"   # preferencias que se eligen desde la app (perfil, modo, etc.)

GRUPOS = {"lider": "accion", "general": "accion", "cedears": "cedear"}


def _fusionar(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = _fusionar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


CLAVE_PREFERENCIAS = "usuario"


def _prefs_en_db(path: Path | None) -> bool:
    from . import db
    return path is None and db.hay_db()


def preferencias(path: Path | None = None) -> dict[str, Any]:
    """Preferencias del dueño. Con DATABASE_URL: tabla `preferencias`, clave 'usuario' (las elige en la web);
    si no, data/usuario.yaml. Pasar `path` fuerza el archivo."""
    if _prefs_en_db(path):
        from . import db
        valor = db.kv_get("preferencias", CLAVE_PREFERENCIAS, {})
        return valor if isinstance(valor, dict) else {}
    p = path or USUARIO_PATH
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def guardar_preferencias(cambios: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Guarda (fusionando) preferencias del usuario. Pisan a settings.yaml al cargar."""
    nuevo = _fusionar(preferencias(path), cambios)
    if _prefs_en_db(path):
        from . import db
        db.kv_set("preferencias", CLAVE_PREFERENCIAS, nuevo)
        return nuevo
    p = path or USUARIO_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(nuevo, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return nuevo


def load_settings(path: Path | None = None, usuario: Path | None = None) -> dict[str, Any]:
    with open(path or ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        base = yaml.safe_load(f)
    return _fusionar(base, preferencias(usuario)) if path is None or usuario else base


def _normalizar(item: dict[str, Any], grupo: str) -> dict[str, Any]:
    tipo = GRUPOS[grupo]
    a = {"adr": None, "ratio_adr": None, "subyacente": None, **item, "panel": grupo, "tipo": tipo}
    if tipo == "cedear" and not a["subyacente"]:
        a["subyacente"] = a["ticker"]
    return a


def load_universe(path: Path | None = None, grupos: list[str] | None = None) -> list[dict[str, Any]]:
    """Universo combinado. Cada activo trae ticker, sector, panel (lider/general/cedears) y tipo (accion/cedear)."""
    with open(path or ROOT / "config" / "universe.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if "acciones" in raw and "lider" not in raw:  # formato viejo
        raw = {"lider": raw["acciones"]}
    elegidos = grupos or list(GRUPOS)
    out, vistos = [], set()
    for g in elegidos:
        for item in raw.get(g) or []:
            if item["ticker"] in vistos:
                continue
            vistos.add(item["ticker"])
            out.append(_normalizar(item, g))
    return out


def sector_map(universe: list[dict[str, Any]]) -> dict[str, str]:
    return {a["ticker"]: a["sector"] for a in universe}


def tipo_map(universe: list[dict[str, Any]]) -> dict[str, str]:
    return {a["ticker"]: a["tipo"] for a in universe}


def load_eventos(path: Path | None = None) -> list[dict[str, Any]]:
    """Calendario de eventos (config/eventos.yaml). Si no existe o está vacío, lista vacía."""
    p = path or ROOT / "config" / "eventos.yaml"
    if not p.exists():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return list(raw.get("eventos") or [])
