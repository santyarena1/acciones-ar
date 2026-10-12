"""Pesos objetivo del portfolio y generación de órdenes sugeridas.

Lógica:
- score < vender            -> peso objetivo 0 (salir)
- vender <= score < comprar -> mantener el peso actual (con tope por acción)
- score >= comprar          -> recibe asignación nueva, proporcional a (score - comprar + 5)
Después se aplican topes por acción y por sector; lo que sobra queda en caja.
"""
from __future__ import annotations

import math

import pandas as pd


def _cap_and_redistribute(raw: dict[str, float], budget: float, cap: float, max_iter: int = 20) -> dict[str, float]:
    """Reparte `budget` proporcional a `raw` sin que nadie supere `cap`."""
    alloc = {t: 0.0 for t in raw}
    libres = {t: w for t, w in raw.items() if w > 0}
    restante = budget
    for _ in range(max_iter):
        if not libres or restante <= 1e-9:
            break
        tot = sum(libres.values())
        topados = {}
        for t, w in libres.items():
            propuesta = restante * w / tot
            if alloc[t] + propuesta >= cap:
                topados[t] = cap - alloc[t]
        if not topados:
            for t, w in libres.items():
                alloc[t] += restante * w / tot
            restante = 0.0
            break
        for t, extra in topados.items():
            alloc[t] = cap
            restante -= extra
            libres.pop(t)
    return alloc


def build_targets(scores: pd.DataFrame, pesos_actuales: dict[str, float], sectores: dict[str, str],
                  settings: dict) -> dict[str, float]:
    """scores: DataFrame con índice ticker y columna 'score'. Devuelve {ticker: peso objetivo}."""
    u, p = settings["umbrales"], settings["portfolio"]
    cap, sec_cap = p["peso_max_accion"], p["peso_max_sector"]
    targets: dict[str, float] = {}
    compras: dict[str, float] = {}

    tickers = set(scores.index) | set(pesos_actuales)
    for t in tickers:
        s = scores["score"].get(t, float("nan"))
        actual = pesos_actuales.get(t, 0.0)
        if s is None or (isinstance(s, float) and math.isnan(s)):
            targets[t] = min(actual, cap)  # sin datos: no tocar (salvo tope)
        elif s < u["vender"]:
            targets[t] = 0.0
        elif s < u["comprar"]:
            targets[t] = min(actual, cap)
        else:
            compras[t] = s - u["comprar"] + 5

    presupuesto = max(0.0, 1.0 - p["caja_minima"] - sum(targets.values()))
    targets.update(_cap_and_redistribute(compras, presupuesto, cap))

    # Topes por sector: se escala hacia abajo; el excedente queda en caja
    por_sector: dict[str, float] = {}
    for t, w in targets.items():
        por_sector[sectores.get(t, "otros")] = por_sector.get(sectores.get(t, "otros"), 0.0) + w
    for sec, total in por_sector.items():
        if total > sec_cap:
            f = sec_cap / total
            for t in targets:
                if sectores.get(t, "otros") == sec:
                    targets[t] *= f
    # redondeo hacia abajo: nunca superar topes por redondear
    return {t: math.floor(w * 1e4) / 1e4 for t, w in targets.items()}


def generate_orders(targets: dict[str, float], posiciones: dict[str, dict], caja_ars: float,
                    precios_ars: dict[str, float], settings: dict) -> pd.DataFrame:
    """posiciones: {ticker: {"cantidad": int, ...}}. Devuelve DataFrame de órdenes (ventas primero)."""
    p = settings["portfolio"]
    valor_total = caja_ars + sum(
        pos["cantidad"] * precios_ars.get(t, 0.0) for t, pos in posiciones.items()
    )
    filas = []
    for t, w in targets.items():
        precio = precios_ars.get(t)
        if not precio or precio <= 0:
            continue
        cant_actual = posiciones.get(t, {}).get("cantidad", 0)
        diff = w * valor_total - cant_actual * precio
        if w == 0 and cant_actual > 0:
            cant, lado = cant_actual, "VENDER"
        elif diff > 0:
            cant, lado = math.floor(diff / precio), "COMPRAR"
        else:
            cant, lado = min(cant_actual, math.floor(-diff / precio)), "VENDER"
        monto = cant * precio
        if cant <= 0 or monto < p["orden_minima_ars"]:
            continue
        filas.append({
            "ticker": t, "lado": lado, "cantidad": int(cant), "precio_ref": round(precio, 2),
            "monto_ars": round(monto, 0), "peso_objetivo": w,
            "peso_actual": round(cant_actual * precio / valor_total, 4) if valor_total else 0.0,
        })
    df = pd.DataFrame(filas, columns=["ticker", "lado", "cantidad", "precio_ref", "monto_ars",
                                      "peso_objetivo", "peso_actual"])
    if df.empty:
        return df
    df["_o"] = (df["lado"] == "COMPRAR").astype(int)
    return df.sort_values(["_o", "monto_ars"], ascending=[True, False]).drop(columns="_o").reset_index(drop=True)
