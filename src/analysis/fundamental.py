"""Score fundamental 0-100.

Recibe un dict de métricas (ratios adimensionales o en USD) y devuelve score + cobertura.
Bloques: calidad 30%, valuación 30%, salud financiera 25%, crecimiento 15%.
Para bancos no se usan EV/EBITDA ni deuda neta/EBITDA (no aplican).
"""
from __future__ import annotations

import math

import numpy as np

# métrica: (valor "malo", valor "bueno"). Interpolación lineal y recorte a [0, 1].
RANGOS = {
    "pe": (25.0, 6.0),
    "ev_ebitda": (12.0, 4.0),
    "pb": (3.0, 0.6),
    "fcf_yield": (0.0, 0.10),
    "roe": (0.0, 0.20),
    "operating_margin": (0.0, 0.25),
    "net_debt_ebitda": (3.5, 0.0),
    "revenue_growth": (-0.10, 0.20),
}

BLOQUES = {
    "calidad": (["roe", "operating_margin"], 0.30),
    "valuacion": (["pe", "ev_ebitda", "pb", "fcf_yield"], 0.30),
    "salud": (["net_debt_ebitda"], 0.25),
    "crecimiento": (["revenue_growth"], 0.15),
}

NO_APLICA = {"bancos": {"ev_ebitda", "net_debt_ebitda"}, "financiero": {"net_debt_ebitda"}}


def lin(x: float, malo: float, bueno: float) -> float:
    if bueno == malo:
        return 0.5
    return float(min(1.0, max(0.0, (x - malo) / (bueno - malo))))


def _valido(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def metric_score(nombre: str, valor: float) -> float:
    # P/E o EV/EBITDA negativos = pérdidas: peor caso
    if nombre in ("pe", "ev_ebitda") and valor <= 0:
        return 0.0
    malo, bueno = RANGOS[nombre]
    return lin(valor, malo, bueno)


def fundamental_score(metrics: dict, sector: str | None = None, excluir_extra: set[str] | None = None) -> dict:
    """`excluir_extra`: métricas que no se puntúan en absoluto (ej. ventas nominales en pesos de las locales)."""
    excluir = NO_APLICA.get(sector or "", set()) | (excluir_extra or set())
    aplicables = [m for m in RANGOS if m not in excluir]
    presentes = {m: metrics[m] for m in aplicables if _valido(metrics.get(m))}
    cobertura = len(presentes) / len(aplicables) if aplicables else 0.0

    bloques: dict[str, float] = {}
    for bloque, (ms, _) in BLOQUES.items():
        vals = [metric_score(m, float(presentes[m])) for m in ms if m in presentes]
        if vals:
            bloques[bloque] = float(np.mean(vals))

    if not bloques:
        return {"score": np.nan, "cobertura": 0.0, "bloques": {}}
    total_w = sum(BLOQUES[b][1] for b in bloques)
    score = sum(v * BLOQUES[b][1] for b, v in bloques.items()) / total_w * 100
    return {
        "score": round(score, 1),
        "cobertura": round(cobertura, 2),
        "bloques": {k: round(v, 2) for k, v in bloques.items()},
    }
