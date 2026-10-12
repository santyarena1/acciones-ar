"""Órdenes sugeridas a partir de pesos objetivo. Función pura.

Garantías (cada una con test):
- VENDER nunca supera la tenencia; COMPRAR nunca supera la caja disponible (las ventas liquidan después,
  salvo `portfolio.usar_ventas_para_compras`), contando slippage del precio límite y comisión.
- Ninguna orden supera `riesgo.orden_maxima_ars` (si está configurado), `riesgo.orden_maxima_pct_cartera` del
  valor total (anti-bug) ni `max_pct_volumen_por_orden` del volumen; todo al precio límite.
- No se generan más de `riesgo.ordenes_max_por_corrida` (ventas primero, después las compras más grandes):
  así la validación de riesgo no bloquea la corrida entera.
- Cantidades en múltiplos del lote (lámina mínima de bonos/ONs; acciones y CEDEARs = 1).
- Precios NaN / <= 0 no generan órdenes.
"""
from __future__ import annotations

import math

import pandas as pd

COLUMNAS = ["ticker", "lado", "cantidad", "precio_ref", "monto_ars", "peso_objetivo", "peso_actual", "mult", "nota"]


def _ok(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def _comision(settings: dict) -> float:
    c = settings.get("costos", {}) or {}
    return (float(c.get("comision_bps", 0)) + float(c.get("derechos_bps", 0))) / 1e4


def _cantidad(w: float, cant_actual: int, precio: float, valor_total: float) -> tuple[int, str]:
    diff = w * valor_total - cant_actual * precio
    if w == 0 and cant_actual > 0:
        return cant_actual, "VENDER"
    if diff > 0:
        return math.floor(diff / precio), "COMPRAR"
    return min(cant_actual, math.floor(-diff / precio)), "VENDER"


def _a_lote(cant: int, lote: int, cant_actual: int, lado: str) -> int:
    if lado == "VENDER" and cant == cant_actual:
        return cant                       # salida total: se vende lo que hay
    return (cant // lote) * lote if lote > 1 else cant


def _recortar(cant: int, precio: float, t: str, vol_ars: dict, settings: dict,
              valor_total: float) -> tuple[int, list[str]]:
    notas = []
    max_pct = settings.get("liquidez", {}).get("max_pct_volumen_por_orden")
    if vol_ars and max_pct and vol_ars.get(t):
        tope = math.floor(vol_ars[t] * max_pct / precio)
        if cant > tope:
            cant, notas = tope, notas + ["recortada por liquidez"]
    r = settings.get("riesgo", {})
    topes = [r.get("orden_maxima_ars")]   # absoluto: opcional (null = sin tope, política del usuario)
    if r.get("orden_maxima_pct_cartera") and valor_total > 0:
        topes.append(r["orden_maxima_pct_cartera"] * valor_total)   # anti-bug, no es estrategia
    for monto in [m for m in topes if m]:
        tope = math.floor(monto / (1 + r.get("slippage_limite", 0.0)) / precio)
        if cant > tope:
            cant, notas = tope, notas + ["recortada por monto máximo por orden"]
    return cant, notas


def _orden(t: str, w: float, pos: dict, precio: float, valor_total: float, ctx: dict) -> dict | None:
    cant_actual = int(pos.get("cantidad", 0) or 0)
    cant, lado = _cantidad(w, cant_actual, precio, valor_total)
    cant, notas = _recortar(cant, precio, t, ctx["vol"], ctx["settings"], valor_total)
    cant = _a_lote(cant, int(ctx["lotes"].get(t, 1) or 1), cant_actual, lado)
    if cant <= 0 or cant * precio < ctx["settings"]["portfolio"]["orden_minima_ars"]:
        return None
    return {"ticker": t, "lado": lado, "cantidad": int(cant), "precio_ref": round(ctx["px"][t], 2),
            "monto_ars": round(cant * precio, 0), "peso_objetivo": w,
            "peso_actual": round(cant_actual * precio / valor_total, 4) if valor_total else 0.0,
            "mult": ctx["mult"].get(t, 1.0), "nota": "; ".join(notas)}


def _ajustar_a_caja(df: pd.DataFrame, caja: float, settings: dict, lotes: dict) -> pd.DataFrame:
    """Achica las compras (proporcionalmente) para que entren en la caja, con slippage y comisión."""
    compras = df["lado"] == "COMPRAR"
    if not compras.any():
        return df
    disponible = max(0.0, caja)
    if settings["portfolio"].get("usar_ventas_para_compras", False):
        disponible += float(df.loc[~compras, "monto_ars"].sum()) * (1 - _comision(settings))
    disponible /= 1 + settings.get("riesgo", {}).get("slippage_limite", 0.0) + _comision(settings)
    total = float(df.loc[compras, "monto_ars"].sum())
    if total <= disponible:
        return df
    f, out = disponible / total, df.copy()
    for i in out.index[compras]:
        unit = out.at[i, "monto_ars"] / out.at[i, "cantidad"]
        cant = _a_lote(math.floor(out.at[i, "cantidad"] * f), int(lotes.get(out.at[i, "ticker"], 1) or 1), -1, "COMPRAR")
        out.at[i, "cantidad"], out.at[i, "monto_ars"] = cant, round(cant * unit, 0)
        out.at[i, "nota"] = "; ".join(x for x in (out.at[i, "nota"], "recortada por caja disponible") if x)
    minimo = settings["portfolio"]["orden_minima_ars"]
    return out[(out["lado"] == "VENDER") | ((out["cantidad"] > 0) & (out["monto_ars"] >= minimo))]


def generate_orders(targets: dict[str, float], posiciones: dict[str, dict], caja_ars: float,
                    precios_ars: dict[str, float], settings: dict,
                    vol_ars: dict[str, float] | None = None,
                    multiplicador: dict[str, float] | None = None,
                    lotes: dict[str, int] | None = None) -> pd.DataFrame:
    """posiciones: {ticker: {"cantidad": int, ...}}. Devuelve DataFrame de órdenes (ventas primero).
    `multiplicador`: precio por unidad = precio_ref * mult (bonos cotizan cada 100 VN -> 0.01).
    `lotes`: múltiplo de cantidad por ticker (lámina mínima)."""
    mult, lotes = multiplicador or {}, lotes or {}
    unit = {t: px * mult.get(t, 1.0) for t, px in precios_ars.items() if _ok(px)}
    valor_total = caja_ars + sum(pos["cantidad"] * unit.get(t, 0.0) for t, pos in posiciones.items())
    ctx = {"vol": vol_ars or {}, "settings": settings, "lotes": lotes, "px": precios_ars, "mult": mult}
    filas = [f for t, w in targets.items()
             if t in unit and (f := _orden(t, w, posiciones.get(t, {}), unit[t], valor_total, ctx))]
    df = pd.DataFrame(filas, columns=COLUMNAS)
    if df.empty:
        return df
    df = _ajustar_a_caja(df, caja_ars, settings, lotes)
    df = df.assign(_o=(df["lado"] == "COMPRAR").astype(int))
    df = df.sort_values(["_o", "monto_ars"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)
    maximo = settings.get("riesgo", {}).get("ordenes_max_por_corrida")
    return df.head(maximo).reset_index(drop=True) if maximo else df
