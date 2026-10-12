"""Validación de órdenes contra límites de riesgo duros. Se corre SIEMPRE antes de enviar."""
from __future__ import annotations

import math

import pandas as pd


class RiskError(Exception):
    pass


def limit_price(lado: str, precio_ref: float, slippage: float) -> float:
    """Compra: último +slippage; venta: último -slippage. Redondeo a 2 decimales en contra nuestra."""
    if lado == "COMPRAR":
        return math.floor(round(precio_ref * (1 + slippage) * 100, 6)) / 100
    return math.ceil(round(precio_ref * (1 - slippage) * 100, 6)) / 100


def validate_orders(ordenes: pd.DataFrame, settings: dict) -> pd.DataFrame:
    r = settings["riesgo"]
    if ordenes.empty:
        return ordenes
    requeridas = {"ticker", "lado", "cantidad", "precio_ref"}
    faltan = requeridas - set(ordenes.columns)
    if faltan:
        raise RiskError(f"Faltan columnas en las órdenes: {sorted(faltan)}")
    if len(ordenes) > r["ordenes_max_por_corrida"]:
        raise RiskError(f"{len(ordenes)} órdenes supera el máximo por corrida ({r['ordenes_max_por_corrida']}).")

    out = ordenes.copy()
    if not out["lado"].isin(["COMPRAR", "VENDER"]).all():
        raise RiskError("Lado de orden inválido (solo COMPRAR / VENDER).")
    if (out["cantidad"] <= 0).any() or (out["cantidad"] != out["cantidad"].astype(int)).any():
        raise RiskError("Hay cantidades no enteras o <= 0.")
    if (out["precio_ref"] <= 0).any():
        raise RiskError("Hay precios de referencia <= 0.")

    out["precio_limite"] = [limit_price(l, p, r["slippage_limite"]) for l, p in zip(out["lado"], out["precio_ref"])]
    out["monto_ars"] = out["cantidad"] * out["precio_limite"]
    excedidas = out[out["monto_ars"] > r["orden_maxima_ars"]]
    if not excedidas.empty:
        raise RiskError(
            f"Órdenes por encima del máximo ({r['orden_maxima_ars']:,} ARS): {excedidas['ticker'].tolist()}"
        )
    return out
