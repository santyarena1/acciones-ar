"""Combina score técnico y fundamental según horizonte, traduce a señales y arma alertas."""
from __future__ import annotations

import math


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


NEUTRO = 50.0


def combined_score(tec: float, fund: float, cobertura: float, horizonte: str, settings: dict,
                   aplica_fundamental: bool = True) -> dict:
    """Si faltan fundamentales se usa un valor NEUTRO (50) en su lugar: un dato faltante no puede
    hacer que un activo parezca mejor que uno con balances. ETFs/metales (aplica_fundamental=False)
    se evalúan solo por técnico porque no tienen balances."""
    pesos = settings["pesos_horizonte"][horizonte]
    min_cob = settings["umbrales"]["cobertura_fund_minima"]
    usa_fund = _ok(fund) and cobertura >= min_cob

    if _ok(tec) and usa_fund and aplica_fundamental:
        score = pesos["tecnico"] * tec + pesos["fundamental"] * fund
        nota = ""
    elif _ok(tec) and not aplica_fundamental:
        score = tec
        nota = "ETF / commodity: solo técnico"
    elif _ok(tec):
        score = pesos["tecnico"] * tec + pesos["fundamental"] * NEUTRO
        nota = "sin fundamentales suficientes: técnico + neutro"
    elif usa_fund:
        score = fund
        nota = "sin historia de precios suficiente: solo fundamental"
    else:
        return {"score": float("nan"), "nota": "sin datos"}
    return {"score": round(score, 1), "nota": nota}


SENALES_COMPRA = ("COMPRAR", "AGREGAR")


def signal(score: float, en_cartera: bool, rsi: float | None, settings: dict, liquido: bool = True,
           sobre_sma200: bool | None = None) -> str:
    """Señal con histéresis (`umbrales.histeresis`) para no rotar por ruido entre corridas:
    - lo que NO está en cartera se compra recién con score >= comprar + margen;
    - lo que está en cartera se vende recién con score < vender - margen (entre medio: MANTENER/AGREGAR).
    Con `umbrales.filtro_tendencia` no se abren posiciones nuevas si el precio no está demostradamente sobre
    la SMA200 en USD (sin 200 ruedas de historia tampoco). Lo que ya está en cartera NO se vende por cruzar
    la SMA200: de eso se ocupa la alerta de stop."""
    u = settings["umbrales"]
    if not _ok(score):
        return "SIN DATOS"
    m = float(u.get("histeresis", 0) or 0)
    if en_cartera:
        if score >= u["comprar"]:
            return "MANTENER" if _ok(rsi) and rsi > u["rsi_sobrecompra"] else "AGREGAR"
        return "MANTENER" if score >= u["vender"] - m else "REDUCIR / VENDER"
    if score >= u["comprar"] + m:
        if not liquido:
            return "ILÍQUIDA (no comprar)"
        if u.get("filtro_tendencia") and sobre_sma200 is not True:
            return "ESPERAR (tendencia bajista)" if sobre_sma200 is False else "ESPERAR (sin 200 ruedas de historia)"
        if _ok(rsi) and rsi > u["rsi_sobrecompra"]:
            return "ESPERAR (sobrecompra)"
        return "COMPRAR"
    return "NO COMPRAR" if score >= u["vender"] else "EVITAR"


def alertas(ind: dict, en_cartera: bool, eventos: list[str] | None, settings: dict) -> list[str]:
    """Alertas legibles para un activo. `ind`: última fila de indicadores como dict."""
    a = settings["alertas"]
    out = []
    dist, close, s200 = ind.get("dist_max_52s"), ind.get("close"), ind.get("sma200")
    bajo_sma = _ok(close) and _ok(s200) and close < s200
    if en_cartera and _ok(dist) and dist <= a["stop_desde_maximo"] and bajo_sma:
        out.append(f"REVISAR STOP: {dist:.0%} desde el máximo de 52 semanas y bajo la SMA200")
    vol = ind.get("vol_anual")
    if _ok(vol) and vol >= a["volatilidad_alta"]:
        out.append(f"volatilidad alta ({vol:.0%} anual)")
    for e in eventos or []:
        if e in ("resultado_negativo", "litigio"):
            out.append(f"evento en el reporte semanal: {e.replace('_', ' ')}")
        elif e == "dividendo":
            out.append("anunció dividendo")
    return out
