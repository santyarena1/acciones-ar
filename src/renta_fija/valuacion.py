"""Valuación instrumento por instrumento (puro): precio -> TIR, TEM, duration, paridad, carry.

Unidades: precio por 100 VN. Bonos USD se valúan con el precio de la especie "D" (dólar MEP); si no hay, con el
precio en pesos / MEP implícito. Los CER se valúan en términos reales (flujos x CER_ref / cer_base).
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from . import calculos as c
from .flujos import generar_flujos, inicio_devengamiento
from .parsers import precio_referencia

PARES_MEP = ("AL30", "GD30", "AL29", "GD29", "AL35", "GD35", "AE38", "GD38")
PATRON_LETRA = re.compile(r"^[ST]\d{2}[A-Z]\d$")  # Lecap S16O6 / Boncap T15E7
MESES_ANIO = 12


@dataclass(frozen=True)
class Contexto:
    liquidacion: date
    cer_ref: float | None
    mep: float | None
    inflacion_mensual: float
    devaluacion_mensual: float


def simbolos(ticker: str, terminos: dict[str, Any]) -> tuple[str, str | None]:
    """(símbolo en pesos, símbolo en dólares MEP) en BYMA, que son los mismos que usa IOL."""
    ars = terminos.get("simbolo_ars", ticker)
    usd = terminos.get("simbolo_usd", f"{ticker}D" if terminos.get("moneda") == "USD" else None)
    return ars, usd


def precio_simbolo(cotiz: pd.DataFrame, simbolo: str | None) -> float | None:
    if not simbolo or simbolo not in cotiz.index:
        return None
    f = cotiz.loc[simbolo]
    return precio_referencia(f["bid"], f["ask"], f["ultimo"])


def mep_implicito(cotiz: pd.DataFrame, pares: tuple[str, ...] = PARES_MEP) -> float | None:
    """Dólar MEP implícito: mediana de precio_pesos / precio_D en los soberanos más líquidos."""
    ratios = []
    for t in pares:
        ars, usd = precio_simbolo(cotiz, t), precio_simbolo(cotiz, f"{t}D")
        if ars and usd:
            ratios.append(ars / usd)
    return statistics.median(ratios) if ratios else None


def volumen_nominal(cotiz: pd.DataFrame, simbolo: str | None) -> float | None:
    """Volumen nominal operado hoy (None si el símbolo no cotiza)."""
    if not simbolo or simbolo not in cotiz.index:
        return None
    return float(cotiz.loc[simbolo, "volumen_nominal"] or 0.0)


def spread_puntas(cotiz: pd.DataFrame, simbolo: str | None) -> float | None:
    """(ask - bid) / punta media. None si falta alguna punta."""
    if not simbolo or simbolo not in cotiz.index:
        return None
    bid, ask = cotiz.loc[simbolo, "bid"], cotiz.loc[simbolo, "ask"]
    if not bid or not ask or bid <= 0 or ask <= 0 or pd.isna(bid) or pd.isna(ask):
        return None
    return float((ask - bid) / ((ask + bid) / 2))


def _calidad_precio(terminos: dict[str, Any], cotiz: pd.DataFrame, ars: str, usd: str | None) -> dict[str, Any]:
    """Insumos del filtro de calidad: volumen de la especie que se opera y de la que define la TIR."""
    usa_usd = terminos.get("moneda") == "USD" and precio_simbolo(cotiz, usd) is not None
    return {"vol_nominal_ars": volumen_nominal(cotiz, ars),
            "vol_nominal_tir": volumen_nominal(cotiz, usd if usa_usd else ars),
            "spread_puntas_ars": spread_puntas(cotiz, ars)}


def volumen_efectivo_ars(cotiz: pd.DataFrame, ars: str, usd: str | None, mep: float | None) -> float:
    """Monto operado (ARS) sumando la especie en pesos y la D convertida al MEP."""
    total = 0.0
    for simbolo, fx in ((ars, 1.0), (usd, mep or 0.0)):
        p = precio_simbolo(cotiz, simbolo)
        if p and simbolo in cotiz.index:
            total += float(cotiz.loc[simbolo, "volumen_nominal"]) * p / 100 * fx
    return total


def terminos_dinamicos(letras: pd.DataFrame, conocidos: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Lecaps/Boncaps nuevas que no están en el YAML: pago final = precio x (1+TEA)^(días/365) de argentinadatos."""
    out: dict[str, dict[str, Any]] = {}
    for _, x in letras.iterrows():
        t = x["ticker"]
        if t in conocidos or not PATRON_LETRA.match(t) or not x["precio"] or x["dias"] <= 0:
            continue
        out[t] = {"nombre": f"{'Lecap' if t[0] == 'S' else 'Boncap'} {x['vencimiento']:%m/%Y}",
                  "clase": "lecap" if t[0] == "S" else "boncap", "familia": "tasa_fija", "moneda": "ARS",
                  "vencimiento": x["vencimiento"],
                  "pago_final": round(c.pago_final_desde_tea(x["precio"], x["tea"], int(x["dias"])), 3),
                  "fuente": "dinámico: precio+TEA de argentinadatos", "confianza": "media"}
    return out


def _precios(terminos: dict[str, Any], p_ars: float | None, p_usd: float | None,
             mep: float | None) -> tuple[float | None, float | None]:
    """(precio en la moneda del instrumento, precio en pesos) por 100 VN."""
    if terminos.get("moneda") == "USD":
        precio = p_usd or (p_ars / mep if p_ars and mep else None)
        return precio, p_ars or (precio * mep if precio and mep else None)
    return p_ars, p_ars


def _factor(terminos: dict[str, Any], ctx: Contexto) -> float | None:
    if "cer_base" not in terminos:
        return 1.0
    return ctx.cer_ref / float(terminos["cer_base"]) if ctx.cer_ref else None


def carries(clase: str, tir: float | None, ctx: Contexto) -> tuple[float | None, float | None]:
    """(carry real mensual vs. inflación esperada, carry en USD mensual vs. devaluación esperada)."""
    if tir is None:
        return None, None
    mensual = (1 + tir) ** (1 / MESES_ANIO) - 1
    infl, dev = ctx.inflacion_mensual, ctx.devaluacion_mensual
    if clase == "cer":  # la TIR ya es real
        return mensual, (1 + mensual) * (1 + infl) / (1 + dev) - 1
    if clase in ("soberano_usd", "on_usd"):
        return (1 + mensual) * (1 + dev) / (1 + infl) - 1, mensual
    return c.tasa_real(mensual, infl), c.tasa_real(mensual, dev)


def _metricas(flujos: list[c.Flujo], precio: float, factor: float, liq: date) -> dict[str, float | None]:
    pagos = [(f.fecha, f.total * factor) for f in c.flujos_futuros(flujos, liq)]
    tir = c.xirr(pagos, precio, liq)
    if tir is None:
        return {"tir": None, "duration": None, "convexidad": None}
    return {"tir": tir, "duration": c.duration_modificada(pagos, liq, tir),
            "convexidad": c.convexidad(pagos, liq, tir)}


def evaluar(ticker: str, terminos: dict[str, Any], cotiz: pd.DataFrame, ctx: Contexto) -> dict[str, Any] | None:
    """Fila de análisis de un instrumento. None si ya venció. Sin precio o sin CER queda con TIR vacía."""
    flujos = generar_flujos(terminos)
    futuros = c.flujos_futuros(flujos, ctx.liquidacion)
    if not futuros:
        return None
    ars, usd = simbolos(ticker, terminos)
    precio, precio_ars = _precios(terminos, precio_simbolo(cotiz, ars), precio_simbolo(cotiz, usd), ctx.mep)
    factor = _factor(terminos, ctx)
    m = (_metricas(flujos, precio, factor, ctx.liquidacion) if precio and factor
         else {"tir": None, "duration": None, "convexidad": None})
    vt = c.valor_tecnico(flujos, ctx.liquidacion, inicio_devengamiento(terminos)) * (factor or 0)
    clase = terminos["clase"]
    carry_real, carry_usd = carries(clase, m["tir"], ctx)
    es_ars = terminos.get("moneda") == "ARS"
    return {
        "ticker": ticker, "nombre": terminos.get("nombre", ticker), "clase": clase,
        "familia": terminos.get("familia", clase), "ley": terminos.get("ley"), "par": terminos.get("par"),
        "emisor": terminos.get("emisor"), "moneda": terminos.get("moneda"),
        "tipo_tasa": "real_cer" if clase == "cer" else ("nominal_ars" if es_ars else "usd"),
        "ticker_iol": ars, "ticker_iol_usd": usd, "precio": precio, "precio_ars": precio_ars,
        "precio_usd": (precio_ars / ctx.mep if precio_ars and ctx.mep else None) if es_ars else precio,
        **m, "tem": c.tem_desde_tea(m["tir"]) if es_ars and m["tir"] is not None else None,
        "vencimiento": futuros[-1].fecha, "dias": (futuros[-1].fecha - ctx.liquidacion).days,
        "dias_proximo_pago": (futuros[0].fecha - ctx.liquidacion).days,
        "paridad": c.paridad(precio, vt) if precio and vt else None, "valor_tecnico": vt or None,
        "residual": c.valor_residual(flujos, ctx.liquidacion),
        "volumen_ars": volumen_efectivo_ars(cotiz, ars, usd, ctx.mep), **_calidad_precio(terminos, cotiz, ars, usd),
        "carry_real": carry_real, "carry_usd": carry_usd,
        "fuente_terminos": terminos.get("fuente"), "confianza": terminos.get("confianza"),
    }
