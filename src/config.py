"""Carga de configuración del proyecto."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
REPORTS_DIR = ROOT / "reports"


def load_settings(path: Path | None = None) -> dict[str, Any]:
    with open(path or ROOT / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_universe(path: Path | None = None) -> list[dict[str, Any]]:
    with open(path or ROOT / "config" / "universe.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["acciones"]


def sector_map(universe: list[dict[str, Any]]) -> dict[str, str]:
    return {a["ticker"]: a["sector"] for a in universe}
