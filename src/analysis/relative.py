"""Scores relativos (de sección cruzada): cada activo comparado contra el resto del universo.

El score absoluto dice "¿esta acción está bien?"; el relativo dice "¿está mejor que las demás?".
Para elegir dónde poner la plata, lo segundo importa más. Funciones puras, sin I/O.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .fundamental import BLOQUES, NO_APLICA, RANGOS

# Componentes técnicos relativos: (columna de compute_indicators, mayor es mejor)
COMPONENTES_TEC = {
    "mom_12m_1m": True,
    "mom_6m": True,
    "mom_3m": True,
    "mom_ajustado": True,     # momentum 12-1 / volatilidad: premia subas "limpias"
    "dist_max_52s": True,     # cerca de máximos = fuerza
}


def percentil(s: pd.Series, mayor_es_mejor: bool = True) -> pd.Series:
    """Rango percentil 0..1 ignorando NaN (los NaN quedan NaN)."""
    s = pd.to_numeric(s, errors="coerce")
    r = s.rank(pct=True, ascending=mayor_es_mejor, method="average")
    n = s.notna().sum()
    if n <= 1:
        return r * np.nan
    # reescala para que el peor sea 0 y el mejor 1
    return (r - 1 / n) / (1 - 1 / n)


def tecnico_relativo(ultimos: pd.DataFrame, min_activos: int = 8) -> pd.Series:
    """`ultimos`: una fila por ticker con las columnas de compute_indicators. Devuelve score 0-100."""
    cols = [c for c in COMPONENTES_TEC if c in ultimos.columns]
    if not cols or ultimos[cols].notna().any(axis=1).sum() < min_activos:
        return pd.Series(np.nan, index=ultimos.index)
    pct = pd.DataFrame({c: percentil(ultimos[c], COMPONENTES_TEC[c]) for c in cols})
    return (pct.mean(axis=1, skipna=True) * 100).round(1)


def _metrica_para_rango(nombre: str, s: pd.Series) -> pd.Series:
    """P/E y EV/EBITDA negativos = pérdidas: se mandan al peor lugar del ranking."""
    s = pd.to_numeric(s, errors="coerce")
    if nombre in ("pe", "ev_ebitda"):
        peor = s[s > 0].max() if (s > 0).any() else 0.0
        s = s.where(~(s <= 0), peor * 10 + 1)
    return s


def fundamental_relativo(metricas: pd.DataFrame, grupos: pd.Series, sectores: pd.Series,
                         min_activos: int = 6) -> pd.Series:
    """Percentil de cada métrica dentro de su grupo (accion / cedear), combinado por bloques. 0-100."""
    out = pd.Series(np.nan, index=metricas.index)
    for _, idx in grupos.groupby(grupos).groups.items():
        sub = metricas.loc[idx]
        pct = {}
        for m, (malo, bueno) in RANGOS.items():
            if m not in sub.columns or sub[m].notna().sum() < min_activos:
                continue
            pct[m] = percentil(_metrica_para_rango(m, sub[m]), mayor_es_mejor=bueno > malo)
        if not pct:
            continue
        pdf = pd.DataFrame(pct)
        for t in pdf.index:
            excluir = NO_APLICA.get(sectores.get(t, ""), set())
            out[t] = _combinar_bloques(pdf.loc[t], excluir)
    return out.round(1)


def _combinar_bloques(fila: pd.Series, excluir: set[str]) -> float:
    bloques = {}
    for b, (ms, w) in BLOQUES.items():
        vals = [fila[m] for m in ms if m in fila.index and m not in excluir and pd.notna(fila[m])]
        if vals:
            bloques[b] = (float(np.mean(vals)), w)
    if not bloques:
        return np.nan
    tot = sum(w for _, w in bloques.values())
    return sum(v * w for v, w in bloques.values()) / tot * 100


def mezclar(absoluto: pd.Series, relativo: pd.Series, peso_relativo: float) -> pd.Series:
    """Promedio ponderado; si falta el relativo queda el absoluto (y viceversa)."""
    a, r = absoluto.astype(float), relativo.reindex(absoluto.index).astype(float)
    mix = (1 - peso_relativo) * a + peso_relativo * r
    return mix.fillna(a).fillna(r).round(1)
