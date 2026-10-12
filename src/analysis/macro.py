"""Régimen macro argentino y asignación por clase de activo. Funciones puras, sin I/O.

Señales (cada una 0..1, 1 = favorable para activos argentinos):
- nivel de riesgo país
- cambio del riesgo país en 60 días (si sube fuerte, mal)
- brecha CCL / oficial
- Merval en USD por encima de su SMA200 (tendencia del mercado local en dólares)
"""
from __future__ import annotations

import pandas as pd

from .fundamental import lin

CLASES_ARGENTINAS = ("acciones_ar", "bonos_usd", "pesos")


def _ultimo(s: pd.Series | None) -> float | None:
    if s is None or s.dropna().empty:
        return None
    return float(s.dropna().iloc[-1])


def _cambio(s: pd.Series | None, dias: int) -> float | None:
    if s is None or s.dropna().empty:
        return None
    s = s.dropna()
    ref = s[s.index <= s.index[-1] - pd.Timedelta(days=dias)]
    return float(s.iloc[-1] / ref.iloc[-1] - 1) if not ref.empty and ref.iloc[-1] else None


def regimen_macro(riesgo_pais: pd.Series | None, ccl: pd.Series | None, oficial: pd.Series | None,
                  merval_usd: pd.Series | None, settings: dict) -> dict:
    m = settings["macro"]
    rp, rp_chg = _ultimo(riesgo_pais), _cambio(riesgo_pais, 60)
    ccl_v, of_v = _ultimo(ccl), _ultimo(oficial)
    brecha = ccl_v / of_v - 1 if ccl_v and of_v else None
    señales, motivos = {}, []
    if rp is not None:
        señales["riesgo_pais"] = lin(rp, m["riesgo_pais_malo"], m["riesgo_pais_bueno"])
        motivos.append(f"Riesgo país {rp:.0f} pb")
    if rp_chg is not None:
        señales["riesgo_pais_tendencia"] = lin(rp_chg, m["riesgo_pais_cambio_malo"], 0.0)
        motivos.append(f"riesgo país {'+' if rp_chg >= 0 else ''}{rp_chg:.0%} en 60 días")
    if brecha is not None:
        señales["brecha"] = lin(brecha, m["brecha_mala"], m["brecha_buena"])
        motivos.append(f"brecha CCL/oficial {brecha:.1%}")
    tendencia = _tendencia(merval_usd)
    if tendencia is not None:
        señales["merval_usd"] = float(tendencia)
        motivos.append("Merval en USD " + ("sobre" if tendencia else "debajo de") + " su media de 200 ruedas")
    score = round(100 * sum(señales.values()) / len(señales), 1) if señales else None
    return {
        "regimen": _clasificar(score), "score": score, "riesgo_pais": rp, "riesgo_pais_cambio_60d": rp_chg,
        "ccl": ccl_v, "oficial": of_v, "brecha": brecha, "merval_sobre_sma200": tendencia,
        "señales": {k: round(v, 2) for k, v in señales.items()}, "motivos": motivos,
    }


def _tendencia(serie: pd.Series | None) -> bool | None:
    if serie is None or len(serie.dropna()) < 200:
        return None
    s = serie.dropna()
    return bool(s.iloc[-1] > s.rolling(200).mean().iloc[-1])


def _clasificar(score: float | None) -> str:
    if score is None:
        return "sin datos"
    if score >= 65:
        return "favorable"
    if score <= 35:
        return "adverso"
    return "neutral"


def asignacion_clases(perfil: str, regimen: str, settings: dict) -> dict[str, float]:
    """Pesos objetivo por clase. En régimen adverso se saca peso de Argentina hacia CEDEARs y caja;
    en favorable se suma peso argentino tomándolo de CEDEARs."""
    base = dict(settings["perfiles"][perfil])
    m = settings["macro"]
    f = {"favorable": m["ajuste_favorable"], "adverso": m["ajuste_adverso"]}.get(regimen, 0.0)
    if f == 0:
        return base
    delta = sum(base[c] * f for c in CLASES_ARGENTINAS)
    if f > 0:
        delta = min(delta, base["cedears"])
        escala = delta / sum(base[c] for c in CLASES_ARGENTINAS)
        out = {c: base[c] * (1 + escala) if c in CLASES_ARGENTINAS else base[c] for c in base}
        out["cedears"] = base["cedears"] - delta
    else:
        out = {c: base[c] * (1 + f) if c in CLASES_ARGENTINAS else base[c] for c in base}
        out["cedears"] = base["cedears"] - delta * 0.7
        out["caja"] = base["caja"] - delta * 0.3
    return {c: round(v, 4) for c, v in out.items()}
