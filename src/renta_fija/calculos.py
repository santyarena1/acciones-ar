"""Matemática de renta fija: TIR (XIRR), TEM, duration, convexidad, residual, cupón corrido, paridad.

Todo puro (sin I/O). Convenciones:
- Los flujos son por cada 100 VN ORIGINALES (como cotiza BYMA) y el precio también es por 100 VN.
- Los precios de BYMA son "sucios" (incluyen cupón corrido), así que la TIR se calcula contra el precio tal cual.
- La TIR es efectiva anual con base actual/365: sum(F_i / (1+r)^(dias_i/365)) = precio.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

BASE_DIAS = 365.0
DIAS_MES = 30.0
TIR_MIN, TIR_MAX = -0.99, 50.0
TOLERANCIA = 1e-10
MAX_ITER = 100


@dataclass(frozen=True)
class Flujo:
    """Pago de un bono por 100 VN originales."""
    fecha: date
    interes: float
    amortizacion: float

    @property
    def total(self) -> float:
        return self.interes + self.amortizacion


# ----------------------------------------------------------------------------- días hábiles

def es_habil(d: date, feriados: frozenset[date] | set[date]) -> bool:
    return d.weekday() < 5 and d not in feriados


def sumar_dias_habiles(d: date, n: int, feriados: frozenset[date] | set[date] = frozenset()) -> date:
    """Corre `n` días hábiles (n negativo va para atrás)."""
    paso = 1 if n >= 0 else -1
    restantes = abs(n)
    actual = d
    while restantes > 0:
        actual += timedelta(days=paso)
        if es_habil(actual, feriados):
            restantes -= 1
    return actual


def fecha_liquidacion(operacion: date, feriados: frozenset[date] | set[date] = frozenset(),
                      plazo: int = 1) -> date:
    """Liquidación T+plazo hábiles. Si `operacion` cae en feriado/fin de semana, los precios son del último
    cierre, así que se cuenta desde el hábil anterior (misma convención que argentinadatos)."""
    base = operacion if es_habil(operacion, feriados) else sumar_dias_habiles(operacion, -1, feriados)
    return sumar_dias_habiles(base, plazo, feriados)


# ----------------------------------------------------------------------------- flujos

def flujos_futuros(flujos: Iterable[Flujo], liquidacion: date) -> list[Flujo]:
    """Pagos que todavía cobra quien liquida en `liquidacion` (estrictamente posteriores)."""
    return sorted((f for f in flujos if f.fecha > liquidacion), key=lambda f: f.fecha)


def valor_residual(flujos: Iterable[Flujo], liquidacion: date) -> float:
    """Capital pendiente por 100 VN originales."""
    return sum(f.amortizacion for f in flujos_futuros(flujos, liquidacion))


def interes_corrido(flujos: Iterable[Flujo], liquidacion: date, inicio_devengamiento: date) -> float:
    """Cupón corrido lineal: interés del próximo pago × fracción del período transcurrido."""
    todos = sorted(flujos, key=lambda f: f.fecha)
    futuros = [f for f in todos if f.fecha > liquidacion]
    if not futuros:
        return 0.0
    pasados = [f.fecha for f in todos if f.fecha <= liquidacion]
    desde = pasados[-1] if pasados else inicio_devengamiento
    largo = (futuros[0].fecha - desde).days
    if largo <= 0:
        return 0.0
    transcurrido = max(0, (liquidacion - desde).days)
    return futuros[0].interes * transcurrido / largo


def valor_tecnico(flujos: Iterable[Flujo], liquidacion: date, inicio_devengamiento: date) -> float:
    lista = list(flujos)
    return valor_residual(lista, liquidacion) + interes_corrido(lista, liquidacion, inicio_devengamiento)


def paridad(precio: float, vt: float) -> float | None:
    return precio / vt if vt > 0 else None


# ----------------------------------------------------------------------------- TIR

def _anios(liquidacion: date, d: date) -> float:
    return (d - liquidacion).days / BASE_DIAS


def valor_presente(pagos: list[tuple[date, float]], liquidacion: date, tir: float) -> float:
    return sum(m / (1 + tir) ** _anios(liquidacion, d) for d, m in pagos)


def _derivada_vp(pagos: list[tuple[date, float]], liquidacion: date, tir: float) -> float:
    return sum(-_anios(liquidacion, d) * m / (1 + tir) ** (_anios(liquidacion, d) + 1) for d, m in pagos)


def _biseccion(pagos: list[tuple[date, float]], liquidacion: date, precio: float) -> float | None:
    lo, hi = TIR_MIN, TIR_MAX
    f_lo = valor_presente(pagos, liquidacion, lo) - precio
    f_hi = valor_presente(pagos, liquidacion, hi) - precio
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = valor_presente(pagos, liquidacion, mid) - precio
        if abs(f_mid) < TOLERANCIA:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def xirr(pagos: list[tuple[date, float]], precio: float, liquidacion: date, semilla: float = 0.1) -> float | None:
    """TIR efectiva anual que iguala el VP de `pagos` (fecha, monto) con `precio`. None si no converge."""
    pagos = [(d, m) for d, m in pagos if d > liquidacion and m != 0]
    if not pagos or precio <= 0:
        return None
    r = semilla
    for _ in range(MAX_ITER):
        f = valor_presente(pagos, liquidacion, r) - precio
        df = _derivada_vp(pagos, liquidacion, r)
        if df == 0 or not math.isfinite(df):
            break
        nuevo = r - f / df
        if not math.isfinite(nuevo) or nuevo <= TIR_MIN:
            break
        if abs(nuevo - r) < TOLERANCIA:
            return nuevo
        r = nuevo
    return _biseccion(pagos, liquidacion, precio)


def tir_flujos(flujos: Iterable[Flujo], precio: float, liquidacion: date, factor: float = 1.0) -> float | None:
    """TIR de un bono. `factor` multiplica los flujos (p.ej. coeficiente CER para TIR real)."""
    pagos = [(f.fecha, f.total * factor) for f in flujos_futuros(flujos, liquidacion)]
    return xirr(pagos, precio, liquidacion)


# ----------------------------------------------------------------------------- duration / convexidad

def duration_macaulay(pagos: list[tuple[date, float]], liquidacion: date, tir: float) -> float | None:
    pagos = [(d, m) for d, m in pagos if d > liquidacion]
    vp = valor_presente(pagos, liquidacion, tir)
    if vp <= 0:
        return None
    return sum(_anios(liquidacion, d) * m / (1 + tir) ** _anios(liquidacion, d) for d, m in pagos) / vp


def duration_modificada(pagos: list[tuple[date, float]], liquidacion: date, tir: float) -> float | None:
    """Sensibilidad del precio a la TIR (años): dP/P ≈ -DM · Δtir."""
    dmac = duration_macaulay(pagos, liquidacion, tir)
    return None if dmac is None else dmac / (1 + tir)


def convexidad(pagos: list[tuple[date, float]], liquidacion: date, tir: float) -> float | None:
    pagos = [(d, m) for d, m in pagos if d > liquidacion]
    vp = valor_presente(pagos, liquidacion, tir)
    if vp <= 0:
        return None
    suma = sum(_anios(liquidacion, d) * (_anios(liquidacion, d) + 1) * m
               / (1 + tir) ** (_anios(liquidacion, d) + 2) for d, m in pagos)
    return suma / vp


# ----------------------------------------------------------------------------- tasas en pesos

def tem_cupon_cero(precio: float, pago_final: float, dias: int) -> float | None:
    """TEM de una letra cupón cero: (pago/precio)^(30/días) - 1."""
    if precio <= 0 or dias <= 0:
        return None
    return (pago_final / precio) ** (DIAS_MES / dias) - 1


def tea_desde_tem(tem: float) -> float:
    return (1 + tem) ** (BASE_DIAS / DIAS_MES) - 1


def tem_desde_tea(tea: float) -> float:
    return (1 + tea) ** (DIAS_MES / BASE_DIAS) - 1


def tna_simple(precio: float, pago_final: float, dias: int) -> float | None:
    """TNA (base 365) como la publica el mercado para Lecaps."""
    if precio <= 0 or dias <= 0:
        return None
    return (pago_final / precio - 1) * BASE_DIAS / dias


def pago_final_desde_tea(precio: float, tea: float, dias: int) -> float:
    """Reconstruye el pago final de una letra a partir de precio y TEA publicados (para completar términos)."""
    return precio * (1 + tea) ** (dias / BASE_DIAS)


def tasa_real(tasa_nominal: float, inflacion: float) -> float:
    """Fisher exacto en la misma base (mensual con mensual, anual con anual)."""
    return (1 + tasa_nominal) / (1 + inflacion) - 1
