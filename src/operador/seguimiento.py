"""Seguimiento del rendimiento: ¿le gana el operador a no hacer nada? ¿hay una caída fuerte? Funciones puras.

- Rendimiento del operador ponderado por tiempo (TWR): los depósitos no cuentan como ganancia.
  r = (valor_hoy - aporte_del_período) / valor_anterior - 1 ; índice = índice_anterior * (1 + r)
- "No hacer nada": mitad S&P 500 (CEDEAR SPY, en pesos) y mitad Merval, comprados el día que arrancó el operador.
- Caída fuerte: el índice cae más que `umbral` desde su máximo -> aviso (una sola vez por cada máximo). No vende.
"""
from __future__ import annotations


def iniciar(valor: float, precios_bm: dict[str, float]) -> dict:
    return {"indice": 1.0, "pico": 1.0, "valor": valor, "bm_base": dict(precios_bm), "bm_indice": 1.0,
            "alertado": False}


def indice_benchmark(base: dict[str, float], precios: dict[str, float]) -> float | None:
    partes = [precios[k] / base[k] for k in base if base.get(k) and precios.get(k)]
    return sum(partes) / len(partes) if partes else None


def actualizar(estado: dict | None, valor: float, aporte: float, precios_bm: dict[str, float],
               umbral_caida: float = -0.15) -> tuple[dict, str | None]:
    """Devuelve (estado nuevo, aviso de caída o None). `aporte`: depósitos (+) / retiros (-) desde la foto anterior."""
    if not estado or not estado.get("valor"):
        return iniciar(valor, precios_bm), None
    r = (valor - aporte) / estado["valor"] - 1 if estado["valor"] > 0 else 0.0
    indice = estado["indice"] * (1 + r)
    pico = max(estado["pico"], indice)
    bm = indice_benchmark(estado.get("bm_base") or {}, precios_bm) or estado.get("bm_indice", 1.0)
    caida = indice / pico - 1
    nuevo = {**estado, "indice": indice, "pico": pico, "valor": valor, "bm_indice": bm}
    aviso = None
    if caida <= umbral_caida and not estado.get("alertado"):
        aviso = (f"La cartera cae {caida:.0%} desde su máximo (sin contar tus depósitos). El operador no vende por "
                 "esto: sigue su análisis. Te aviso para que lo sepas.")
        nuevo["alertado"] = True
    elif indice >= pico:
        nuevo["alertado"] = False          # nuevo máximo: se rearma el aviso
    return nuevo, aviso


def resumen(estado: dict | None) -> dict:
    if not estado:
        return {}
    op, bm = estado["indice"] - 1, estado.get("bm_indice", 1.0) - 1
    return {"operador": op, "no_hacer_nada": bm, "diferencia": op - bm, "caida_desde_maximo": estado["indice"] / estado["pico"] - 1}
