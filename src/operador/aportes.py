"""Depósitos del dueño: detectarlos y descontarlos del rendimiento. Funciones puras.

Entre dos corridas la caja solo puede cambiar por: ventas que se acreditan, compras que se debitan, comisiones,
cupones/dividendos y depósitos o retiros del dueño. Si la caja sube bastante más de lo que explican las ventas,
es un depósito. Cupones y dividendos son chicos frente al umbral, y si alguno lo supera se cuenta como aporte
(error conservador: el rendimiento informado queda un poco más bajo, nunca más alto).
"""
from __future__ import annotations


def detectar_aporte(caja_anterior: float | None, caja_ahora: float, ventas_desde: float, compras_desde: float,
                    valor_total: float, umbral_min: float = 10_000, umbral_pct: float = 0.02) -> float:
    """Monto del depósito (>0), retiro (<0) o 0. `ventas_desde`/`compras_desde`: montos operados desde la corrida
    anterior que todavía pueden estar acreditándose (incluye las del día hábil previo por la liquidación T+1)."""
    if caja_anterior is None:
        return 0.0
    explicado = caja_anterior + ventas_desde - compras_desde
    diferencia = caja_ahora - explicado
    umbral = max(umbral_min, umbral_pct * max(valor_total, 0))
    if diferencia > umbral:
        return round(diferencia, 0)
    # un retiro: la caja baja sin compras que lo expliquen (y sin ventas pendientes de acreditar)
    if diferencia < -umbral and ventas_desde == 0:
        return round(diferencia, 0)
    return 0.0


def rendimiento(valor_total: float, aportes_netos: float) -> tuple[float, float | None]:
    """(ganancia en $, ganancia en %) descontando lo que puso el dueño."""
    if not aportes_netos or aportes_netos <= 0:
        return 0.0, None
    g = valor_total - aportes_netos
    return g, g / aportes_netos
