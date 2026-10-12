"""Rotación por sector / región. Funciones puras, sin I/O.

Cada grupo (tecnología, energía, Brasil, emergentes, ...) se mide con un ETF de referencia (`proxy`). Puntaje del
grupo = momentum ajustado por riesgo: (peso_12m * retorno 12 meses sin el último + peso_3m * retorno 3 meses) /
volatilidad anual de 6 meses. Los grupos se ordenan entre sí (percentil) y cada uno recibe un multiplicador:
el del medio 1x, el mejor `mult_max`, el peor `mult_min`. Ese multiplicador escala el tamaño que el score le da a
cada CEDEAR del grupo; los topes por activo y por sector siguen valiendo.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

RUEDAS_12M, RUEDAS_1M, RUEDAS_3M, RUEDAS_6M = 252, 21, 63, 126
DEFAULTS = {"peso_12m": 0.5, "peso_3m": 0.5, "vol_minima": 0.05, "mult_min": 0.5, "mult_max": 1.75,
            "min_grupos": 4, "grupos": {}}


def cfg_rotacion(settings: dict) -> dict:
    r = (settings.get("tactico") or {}).get("rotacion") or {}
    return {**DEFAULTS, **r}


def momentum_ajustado(px: pd.Series | None, cfg: dict) -> float | None:
    """Puntaje de un grupo con su serie de precios en USD hasta la fecha de análisis."""
    if px is None:
        return None
    s = px.dropna()
    if len(s) < RUEDAS_12M + 1 or (s <= 0).any():
        return None
    r12 = float(s.iloc[-RUEDAS_1M - 1] / s.iloc[-RUEDAS_12M - 1] - 1)
    r3 = float(s.iloc[-1] / s.iloc[-RUEDAS_3M - 1] - 1)
    vol = float(np.log(s.iloc[-RUEDAS_6M - 1:]).diff().dropna().std() * math.sqrt(252))
    return (cfg["peso_12m"] * r12 + cfg["peso_3m"] * r3) / max(vol, cfg["vol_minima"])


def multiplicadores(puntajes: dict[str, float], mult_min: float, mult_max: float) -> dict[str, float]:
    """Percentil entre grupos -> multiplicador lineal por tramos: 0 -> mult_min, 0.5 -> 1, 1 -> mult_max."""
    validos = {g: p for g, p in puntajes.items() if p is not None and not math.isnan(p)}
    if len(validos) < 2:
        return dict.fromkeys(validos, 1.0)
    orden = sorted(validos, key=validos.get)
    n = len(orden)
    out = {}
    for i, g in enumerate(orden):
        p = i / (n - 1)
        m = 1 - (0.5 - p) * 2 * (1 - mult_min) if p < 0.5 else 1 + (p - 0.5) * 2 * (mult_max - 1)
        out[g] = round(m, 3)
    return out


def grupo_de(ticker: str, sector: str | None, grupos: dict[str, dict]) -> str | None:
    """Primero por ticker explícito, después por sector del universo."""
    for g, d in grupos.items():
        if ticker in (d.get("tickers") or []):
            return g
    for g, d in grupos.items():
        if sector and sector in (d.get("sectores") or []):
            return g
    return None


def proxies(grupos: dict[str, dict]) -> list[str]:
    return sorted({d["proxy"] for d in grupos.values() if d.get("proxy")})


def evaluar_grupos(series: dict[str, pd.Series], cfg: dict) -> dict[str, dict]:
    """{grupo: {'puntaje', 'multiplicador'}}. Con menos de `min_grupos` medibles no se inclina nada (todo 1x)."""
    grupos = cfg.get("grupos") or {}
    punt = {g: momentum_ajustado(series.get(d.get("proxy")), cfg) for g, d in grupos.items()}
    medibles = {g: p for g, p in punt.items() if p is not None}
    mult = multiplicadores(medibles, cfg["mult_min"], cfg["mult_max"]) if len(medibles) >= cfg["min_grupos"] \
        else dict.fromkeys(medibles, 1.0)
    return {g: {"puntaje": None if p is None else round(p, 3), "multiplicador": mult.get(g, 1.0)}
            for g, p in punt.items()}


def rotacion(series: dict[str, pd.Series], sectores: dict[str, str], cfg: dict, n_extremos: int = 3) -> dict:
    """Resumen para la corrida: multiplicador por ticker (CEDEARs del universo), grupos que lideran y que
    quedan atrás, y motivos en castellano."""
    ev = evaluar_grupos(series, cfg)
    grupos = cfg.get("grupos") or {}
    por_ticker = {}
    for t, sec in sectores.items():
        g = grupo_de(t, sec, grupos)
        if g is not None and g in ev:
            por_ticker[t] = ev[g]["multiplicador"]
    medidos = sorted([g for g in ev if ev[g]["puntaje"] is not None], key=lambda g: ev[g]["puntaje"], reverse=True)
    fav = [g for g in medidos[:n_extremos] if ev[g]["multiplicador"] > 1]
    cas = [g for g in medidos[::-1][:n_extremos] if ev[g]["multiplicador"] < 1]
    nombre = lambda g: grupos[g].get("nombre", g)  # noqa: E731
    motivos = []
    if fav:
        motivos.append("Vienen mejor (momentum ajustado por riesgo): " + ", ".join(nombre(g) for g in fav)
                       + ": se les da más peso dentro de los CEDEARs")
    if cas:
        motivos.append("Vienen peor: " + ", ".join(nombre(g) for g in cas) + ": se les da menos peso")
    return {"grupos": ev, "mult_por_ticker": por_ticker, "favorecidos": [nombre(g) for g in fav],
            "castigados": [nombre(g) for g in cas], "motivos": motivos}
