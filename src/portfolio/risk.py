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


def _numeros_validos(out: pd.DataFrame) -> None:
    for col in ("cantidad", "precio_ref"):
        v = pd.to_numeric(out[col], errors="coerce")
        if v.isna().any() or not v.map(math.isfinite).all():
            raise RiskError(f"Hay valores vacíos o no numéricos en '{col}'.")
    if out["ticker"].astype(str).str.strip().eq("").any() or out["ticker"].duplicated().any():
        raise RiskError("Ticker vacío o repetido en las órdenes (una sola orden por activo y corrida).")


def _contra_cartera(out: pd.DataFrame, posiciones: dict | None, caja_ars: float | None, settings: dict) -> None:
    if posiciones is not None:
        for _, o in out[out["lado"] == "VENDER"].iterrows():
            tengo = int((posiciones.get(o["ticker"]) or {}).get("cantidad", 0) or 0)
            if o["cantidad"] > tengo:
                raise RiskError(f"Venta de {o['cantidad']} {o['ticker']} supera la tenencia ({tengo}).")
    if caja_ars is not None:
        c = settings.get("costos", {}) or {}
        comision = (float(c.get("comision_bps", 0)) + float(c.get("derechos_bps", 0))) / 1e4
        compras = float(out.loc[out["lado"] == "COMPRAR", "monto_ars"].sum()) * (1 + comision)
        if compras > caja_ars + 1e-6:
            raise RiskError(f"Las compras (${compras:,.0f} con comisión) superan la caja disponible (${caja_ars:,.0f}).")


def _montos_maximos(out: pd.DataFrame, r: dict, valor_total: float | None) -> None:
    """Tope absoluto opcional (`orden_maxima_ars`: null = sin tope) y anti-bug relativo a la cartera
    (`orden_maxima_pct_cartera`, solo si el llamador pasa valor_total)."""
    topes = []
    if r.get("orden_maxima_ars"):
        topes.append((float(r["orden_maxima_ars"]), f"{r['orden_maxima_ars']:,} ARS"))
    if valor_total and r.get("orden_maxima_pct_cartera"):
        topes.append((float(r["orden_maxima_pct_cartera"]) * valor_total,
                      f"{r['orden_maxima_pct_cartera']:.0%} de la cartera"))
    for tope, texto in topes:
        excedidas = out[out["monto_ars"] > tope]
        if not excedidas.empty:
            raise RiskError(f"Órdenes por encima del máximo ({texto}): {excedidas['ticker'].tolist()}")


def validate_orders(ordenes: pd.DataFrame, settings: dict, posiciones: dict | None = None,
                    caja_ars: float | None = None, valor_total: float | None = None) -> pd.DataFrame:
    """Con `posiciones` verifica que ninguna venta supere la tenencia; con `caja_ars`, que las compras (al
    precio límite + comisión) entren en la caja (las ventas no suman: liquidan después); con `valor_total`,
    que ninguna orden supere `orden_maxima_pct_cartera` de la cartera."""
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
    _numeros_validos(out)
    if not out["lado"].isin(["COMPRAR", "VENDER"]).all():
        raise RiskError("Lado de orden inválido (solo COMPRAR / VENDER).")
    if (out["cantidad"] <= 0).any() or (out["cantidad"] != out["cantidad"].astype(int)).any():
        raise RiskError("Hay cantidades no enteras o <= 0.")
    if (out["precio_ref"] <= 0).any():
        raise RiskError("Hay precios de referencia <= 0.")

    out["precio_limite"] = [limit_price(l, p, r["slippage_limite"]) for l, p in zip(out["lado"], out["precio_ref"])]
    mult = out["mult"].fillna(1.0) if "mult" in out.columns else 1.0  # bonos: precio cada 100 VN
    if "mult" in out.columns and ((out["mult"] <= 0) | (out["mult"] > 1)).any():
        raise RiskError("Multiplicador de precio inválido (debe estar entre 0 y 1).")
    out["monto_ars"] = out["cantidad"] * out["precio_limite"] * mult
    _montos_maximos(out, r, valor_total)
    _contra_cartera(out, posiciones, caja_ars, settings)
    return out
