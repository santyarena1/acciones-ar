"""Ajuste de la cartera al tamaño del capital. Función pura.

Con poco capital no se puede diversificar como con mucho: cada posición tiene que valer al menos
`portfolio.posicion_minima_ars` (si no, las comisiones y el redondeo a unidades enteras se comen el resultado).
A partir del valor total y del reparto por clase se calcula cuántas posiciones entran en cada clase, y se suben los
topes por activo para que el presupuesto de cada clase se pueda usar entero. Con más capital, se diversifica solo.
"""
from __future__ import annotations

import copy
import math


def cantidad_posiciones(presupuesto_ars: float, posicion_minima: float, maximo: int) -> int:
    if presupuesto_ars <= 0 or posicion_minima <= 0:
        return 0
    return max(0, min(int(maximo), math.floor(presupuesto_ars / posicion_minima)))


def escalar(settings: dict, valor_total: float, asignacion: dict[str, float]) -> tuple[dict, dict]:
    """Devuelve (settings ajustados, resumen). No modifica `settings`."""
    s = copy.deepcopy(settings)
    p, e = s["portfolio"], s.setdefault("estrategia", {})
    rf = s.setdefault("renta_fija", {})
    pos_min = float(p.get("posicion_minima_ars") or 0)
    if pos_min <= 0 or valor_total <= 0:
        return s, {}
    plata = {c: valor_total * w for c, w in asignacion.items()}
    n_ar = cantidad_posiciones(plata.get("acciones_ar", 0), pos_min, e.get("n_acciones_ar", 8))
    n_ced_max = max(1, round(p.get("max_posiciones_rv", 12) / 2))
    n_ced = cantidad_posiciones(plata.get("cedears", 0), pos_min, n_ced_max)
    max_rf = rf.get("max_instrumentos") or {"bonos_usd": 3, "pesos": 3}
    n_rf = {c: cantidad_posiciones(plata.get(c, 0), pos_min, max_rf.get(c, 3)) for c in ("bonos_usd", "pesos")}

    e["n_acciones_ar"] = n_ar
    p["max_posiciones_rv"] = n_ar + n_ced
    p["max_posiciones_cedears"] = n_ced
    rf["max_instrumentos"] = n_rf
    # topes por activo: que cada clase pueda invertir todo su presupuesto con la cantidad de posiciones que le toca
    por_pos = [asignacion.get(c, 0) / n for c, n in (("acciones_ar", n_ar), ("cedears", n_ced)) if n]
    p["peso_max_accion"] = max(p.get("peso_max_accion", 0.10), *por_pos) if por_pos else p.get("peso_max_accion", 0.10)
    por_rf = [asignacion.get(c, 0) / n for c, n in n_rf.items() if n]
    rf["peso_max_instrumento"] = max(rf.get("peso_max_instrumento", 0.12), *por_rf) if por_rf else \
        rf.get("peso_max_instrumento", 0.12)
    tam_ced = plata.get("cedears", 0) / n_ced if n_ced else 0.0
    resumen = {"posicion_minima": pos_min, "acciones_ar": n_ar, "cedears": n_ced, **n_rf,
               "tamano_cedear": round(tam_ced, 0)}
    return s, resumen


def asequible(precio_unitario: float | None, tamano_posicion: float) -> bool:
    """¿Se puede comprar al menos una unidad sin pasarse del tamaño de la posición?"""
    return bool(precio_unitario) and tamano_posicion > 0 and precio_unitario <= tamano_posicion
