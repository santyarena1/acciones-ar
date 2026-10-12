"""Combina score técnico y fundamental según horizonte y traduce a señales."""
from __future__ import annotations

import math


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def combined_score(tec: float, fund: float, cobertura: float, horizonte: str, settings: dict) -> dict:
    pesos = settings["pesos_horizonte"][horizonte]
    min_cob = settings["umbrales"]["cobertura_fund_minima"]
    usa_fund = _ok(fund) and cobertura >= min_cob

    if _ok(tec) and usa_fund:
        score = pesos["tecnico"] * tec + pesos["fundamental"] * fund
        nota = ""
    elif _ok(tec):
        score = tec
        nota = "sin fundamentales suficientes: solo técnico"
    elif usa_fund:
        score = fund
        nota = "sin historia de precios suficiente: solo fundamental"
    else:
        return {"score": float("nan"), "nota": "sin datos"}
    return {"score": round(score, 1), "nota": nota}


def signal(score: float, en_cartera: bool, rsi: float | None, settings: dict) -> str:
    u = settings["umbrales"]
    if not _ok(score):
        return "SIN DATOS"
    if score >= u["comprar"]:
        if _ok(rsi) and rsi > u["rsi_sobrecompra"]:
            return "MANTENER" if en_cartera else "ESPERAR (sobrecompra)"
        return "AGREGAR" if en_cartera else "COMPRAR"
    if score >= u["vender"]:
        return "MANTENER" if en_cartera else "NO COMPRAR"
    return "REDUCIR / VENDER" if en_cartera else "EVITAR"
