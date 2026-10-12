"""Persistencia de corridas: cada análisis completo queda en reports/corridas/AAAAMMDD_HHMM/.

Archivos: ranking.csv, renta_fija.csv, objetivos.csv, ordenes.csv, meta.json (macro, asignación, cartera,
contexto del reporte semanal) y guia.md. La app web lee de acá: no recalcula nada para mostrar.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
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


def _limpiar(o):
    """JSON no admite NaN/inf ni tipos de numpy/pandas."""
    if isinstance(o, dict):
        return {str(k): _limpiar(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_limpiar(v) for v in o]
    if hasattr(o, "item"):
        o = o.item()
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    return o


def guardar(c: Corrida, base: Path | None = None) -> Path:
    d = (base or CORRIDAS_DIR) / c.stamp
    d.mkdir(parents=True, exist_ok=True)
    c.ranking.to_csv(d / "ranking.csv")
    for nombre, df in (("renta_fija", c.renta_fija), ("objetivos", c.objetivos)):
        if df is not None and not df.empty:
            df.to_csv(d / f"{nombre}.csv")
    if c.ordenes is not None and not c.ordenes.empty:
        c.ordenes.to_csv(d / "ordenes.csv", index=False)
    (d / "meta.json").write_text(json.dumps(_limpiar(c.meta), ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "guia.md").write_text(c.guia, encoding="utf-8")
    c.dir = d
    return d


def _csv(p: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(p, **kw) if p.exists() else pd.DataFrame()


TEXTOS = ("alertas", "eventos", "nota", "senal", "tipo", "panel", "sector")


def _ranking(p: Path) -> pd.DataFrame:
    df = _csv(p, index_col=0)
    for col in TEXTOS:  # en el CSV los textos vacíos vuelven como NaN
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
    return df


def cargar(stamp: str, base: Path | None = None) -> Corrida:
    d = (base or CORRIDAS_DIR) / stamp
    return Corrida(
        stamp=stamp,
        meta=json.loads((d / "meta.json").read_text(encoding="utf-8")),
        ranking=_ranking(d / "ranking.csv"),
        renta_fija=_csv(d / "renta_fija.csv", index_col=0),
        objetivos=_csv(d / "objetivos.csv", index_col=0),
        ordenes=_csv(d / "ordenes.csv"),
        guia=(d / "guia.md").read_text(encoding="utf-8") if (d / "guia.md").exists() else "",
        dir=d,
    )


def listar(base: Path | None = None) -> list[str]:
    d = base or CORRIDAS_DIR
    if not d.exists():
        return []
    return sorted((p.name for p in d.iterdir() if (p / "meta.json").exists()), reverse=True)


def ultima(base: Path | None = None) -> Corrida | None:
    stamps = listar(base)
    return cargar(stamps[0], base) if stamps else None
