"""Qué órdenes ejecutar hoy y qué pedirle al dueño de la cuenta. Funciones puras.

Frecuencia "inteligente": el operador revisa varias veces por día, pero solo opera cuando vale la pena:
- SALIDAS (objetivo 0 en algo que tenemos: score bajo o stop) -> siempre, apenas aparecen.
- ENTRADAS nuevas (algo que no tenemos y el análisis quiere comprar) -> siempre.
- AJUSTES de posiciones existentes -> solo si el desvío supera `banda_no_operar` (ej. 2% de la cartera).
  Un ajuste chico cuesta más en comisiones (~0,6% por lado) de lo que aporta.

Protecciones técnicas (no son topes de estrategia, son contra datos rotos o bugs):
- no repetir en el día una orden ya enviada (mismo ticker y lado), ni según la bitácora ni según el broker
- no operar si el precio del broker se aleja más de `tolerancia_precio` del precio del análisis, si la
  cotización es de otro día o si la punta contra la que operaríamos está lejos
- las compras se achican a la caja disponible (de mayor a menor score) contando el precio límite (slippage) y
  la comisión, y respetando lámina mínima / incremento; las ventas nunca superan lo disponible

Unidades: `precio_ref` es el precio de pantalla (acciones: por unidad; renta fija: cada 100 VN) y `cantidad`
son unidades o VN. Monto en pesos = cantidad * precio_ref * mult (mult 0.01 en renta fija).
"""
from __future__ import annotations

import math
from datetime import date

import pandas as pd

# slippage del precio límite (0,5%) + comisión y derechos (~0,6%) + margen de redondeo
RECARGO_COMPRA_DEFAULT = 0.012
_LADO_IOL = {"compra": "COMPRAR", "venta": "VENDER"}


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return math.nan
    return v


def _peso(x) -> float:
    return 0.0 if x is None else _num(x)


def _desvio(o: pd.Series) -> float:
    return abs(_peso(o.get("peso_objetivo", 0)) - _peso(o.get("peso_actual", 0)))


def clasificar(o: pd.Series, en_cartera: bool) -> str:
    if o["lado"] == "VENDER" and _peso(o.get("peso_objetivo", 0)) == 0:
        return "salida"
    if o["lado"] == "COMPRAR" and not en_cartera:
        return "entrada"
    return "ajuste"


def filtrar_por_banda(ordenes: pd.DataFrame | None, posiciones: dict, banda: float) -> pd.DataFrame:
    if ordenes is None:
        return pd.DataFrame()
    if ordenes.empty:
        return ordenes.assign(motivo=pd.Series(dtype=object))
    out = ordenes.copy()
    out["motivo"] = [clasificar(o, o["ticker"] in posiciones) for _, o in out.iterrows()]
    keep = (out["motivo"] != "ajuste") | (out.apply(_desvio, axis=1) >= banda)
    return out[keep].reset_index(drop=True)


def sin_repetidas(ordenes: pd.DataFrame, ya_enviadas: set[tuple[str, str]]) -> pd.DataFrame:
    if ordenes is None or ordenes.empty:
        return ordenes
    mask = [(t, l) not in ya_enviadas for t, l in zip(ordenes["ticker"], ordenes["lado"])]
    return ordenes[mask].reset_index(drop=True)


def claves_operadas_hoy(operaciones: list[dict] | None, hoy: date) -> set[tuple[str, str]]:
    """(ticker, lado) de las operaciones del broker con fecha `hoy` (salida de iol.parse_operaciones).

    Complementa a la bitácora: si el proceso se cortó entre el envío y el registro, el broker igual la tiene.
    Solo los rechazos no bloquean (una cancelada a mano tampoco se reenvía: decisión del dueño)."""
    claves = set()
    for op in operaciones or []:
        lado = _LADO_IOL.get(str(op.get("tipo") or "").lower())
        if not lado or not op.get("simbolo") or str(op.get("fecha") or "")[:10] != hoy.isoformat():
            continue
        if "rechaz" in str(op.get("estado") or "").lower():
            continue
        claves.add((op["simbolo"], lado))
    return claves


def _cotizacion_vieja(cotizacion: dict, hoy: date | None) -> bool:
    fecha = str(cotizacion.get("fecha") or "")[:10]
    return bool(hoy and fecha and fecha < hoy.isoformat())


def precio_sano(precio_analisis: float, cotizacion: dict | None, tolerancia: float, lado: str | None = None,
                exigir: bool = False, hoy: date | None = None) -> tuple[bool, float]:
    """Compara contra el último precio del broker (misma unidad: renta fija cada 100 VN). Devuelve
    (ok, precio a usar).

    - Sin cotización: ok solo si no se `exigir` (paper); en real (`exigir=True`) no se opera a ciegas.
    - Cotización de otro día (`hoy`): no ok (el último precio es viejo).
    - Con `lado`, la punta contra la que operaríamos (ask para comprar, bid para vender) también tiene que
      estar dentro de la tolerancia (spread enorme = libro vacío o dato roto); con `exigir`, tiene que existir.
    """
    pa = _num(precio_analisis)
    if not pa > 0:
        return False, precio_analisis
    if not cotizacion or not cotizacion.get("ultimoPrecio"):
        return not exigir, precio_analisis
    vivo = _num(cotizacion["ultimoPrecio"])
    if not vivo > 0 or _cotizacion_vieja(cotizacion, hoy) or abs(vivo / pa - 1) > tolerancia:
        return False, vivo if vivo == vivo else precio_analisis
    if lado:
        punta = _num(cotizacion.get("precioVenta" if lado == "COMPRAR" else "precioCompra"))
        if not punta > 0:
            return (not exigir), vivo
        if abs(punta / vivo - 1) > tolerancia:
            return False, vivo
    return True, vivo


def laminas_de_cotizaciones(cotizaciones: dict[str, dict | None]) -> dict[str, tuple[int, int]]:
    """{ticker: (lámina mínima, incremento)} desde las cotizaciones del broker (iol.parse_quote)."""
    out = {}
    for t, q in (cotizaciones or {}).items():
        if not q:
            continue
        lamina, lote = _num(q.get("laminaMinima")), _num(q.get("lote"))
        out[t] = (int(lamina) if lamina >= 1 else 1, int(lote) if lote >= 1 else 1)
    return out


def redondear_a_lamina(cantidad: int, lamina: int = 1, incremento: int = 1, tenencia: int | None = None,
                       lado: str = "COMPRAR") -> int:
    """Cantidad válida para BYMA: múltiplo de `incremento` y >= `lamina` (si no, 0 = no enviar).

    Ventas: nunca más que `tenencia`; vender TODO siempre vale. Si una venta parcial dejaría un remanente
    menor a la lámina (invendible), se vende menos para dejar exactamente una lámina."""
    lamina, incremento = max(1, int(lamina)), max(1, int(incremento))
    q = max(0, int(cantidad))
    if lado == "VENDER" and tenencia is not None:
        q = min(q, max(0, int(tenencia)))
        if q == tenencia:
            return q
        if 0 < tenencia - q < lamina:
            q = tenencia - lamina
    q = (q // incremento) * incremento
    return q if q >= lamina else 0


def _unitario(o: pd.Series) -> float:
    """Pesos por unidad/VN al precio de referencia (NaN si el precio o el mult son inválidos)."""
    mult = _num(o.get("mult", 1.0))
    mult = 1.0 if mult != mult else mult
    return _num(o.get("precio_ref")) * mult


def ajustar_ventas(ordenes: pd.DataFrame, posiciones: dict, laminas: dict[str, tuple[int, int]] | None = None
                   ) -> pd.DataFrame:
    """Ventas: nunca más que lo disponible (cantidad - comprometido) y en láminas válidas. Las que quedan en
    0 se descartan. Sin la tenencia en `posiciones` no se vende (no hay cómo saber qué tenemos)."""
    if ordenes is None or ordenes.empty:
        return ordenes
    laminas = laminas or {}
    filas = []
    for _, o in ordenes.iterrows():
        if o["lado"] == "VENDER":
            pos = posiciones.get(o["ticker"]) or {}
            tenencia = int(pos.get("disponible", pos.get("cantidad", 0)) or 0)
            lamina, inc = laminas.get(o["ticker"], (1, 1))
            q = redondear_a_lamina(int(o["cantidad"]), lamina, inc, tenencia, "VENDER")
            if q <= 0:
                continue
            o = o.copy()
            o["cantidad"] = q
            o["monto_ars"] = round(q * _unitario(o), 0)
        filas.append(o)
    return pd.DataFrame(filas, columns=ordenes.columns).reset_index(drop=True)


def _ordenar_compras(compras: pd.DataFrame, prioridad: dict[str, float]) -> pd.DataFrame:
    """De mayor a menor prioridad (score); NaN al final; empates en el orden original (estable)."""
    p = compras["ticker"].map(lambda t: _num(prioridad.get(t)))
    return compras.assign(_p=p.fillna(-math.inf)).sort_values("_p", ascending=False, kind="mergesort")


def ajustar_a_caja(ordenes: pd.DataFrame, caja: float, prioridad: dict[str, float],
                   recargo: float = RECARGO_COMPRA_DEFAULT, laminas: dict[str, tuple[int, int]] | None = None,
                   monto_minimo: float = 0.0) -> tuple[pd.DataFrame, float]:
    """Achica/saca compras para no gastar más que `caja`. Devuelve (órdenes, faltante en $).

    - Las ventas no suman caja: liquidan después (y el broker puede no ejecutarlas), así que nunca se compra
      con plata de una venta del mismo ciclo.
    - Cada compra cuesta cantidad * precio_ref * mult * (1 + `recargo`): el límite se pone arriba del último
      (slippage) y la comisión sale de la misma caja. Pasar recargo = slippage + comisión de settings.
    - Cantidades en múltiplos de la lámina/incremento (`laminas`); las compras que quedan debajo de
      `monto_minimo` después de achicarse se descartan (no vale la pena la comisión mínima).
    """
    if ordenes is None or ordenes.empty:
        return ordenes, 0.0
    laminas = laminas or {}
    ventas = ordenes[ordenes["lado"] == "VENDER"]
    compras = _ordenar_compras(ordenes[ordenes["lado"] == "COMPRAR"], prioridad)
    restante = max(0.0, _num(caja)) if _num(caja) == _num(caja) else 0.0
    filas, faltante = [], 0.0
    for _, o in compras.iterrows():
        unit, pedida = _unitario(o), int(o["cantidad"])
        if not unit > 0:
            continue  # precio roto: no se compra ni se cuenta como faltante
        lamina, inc = laminas.get(o["ticker"], (1, 1))
        q = redondear_a_lamina(min(pedida, math.floor(restante / (unit * (1 + recargo)))), lamina, inc)
        if q > 0 and q * unit < monto_minimo:
            q = 0  # achicada a algo que no vale la comisión: se descarta entera
        faltante += (pedida - q) * unit
        if q <= 0:
            continue
        o = o.copy()
        o["cantidad"], o["monto_ars"] = q, round(q * unit, 0)
        filas.append(o)
        restante -= q * unit * (1 + recargo)
    cols = list(ordenes.columns)
    compras_ok = pd.DataFrame(filas, columns=compras.columns).drop(columns="_p", errors="ignore")
    return pd.concat([ventas, compras_ok], ignore_index=True)[cols], round(max(0.0, faltante), 0)


def pedido_de_fondos(faltante: float, ranking: pd.DataFrame | None, posiciones: dict, settings: dict) -> dict | None:
    """Si el plan necesita más plata de la que hay, arma un pedido con el porqué (incluye recompras)."""
    minimo = settings.get("operador", {}).get("pedido_fondos_minimo", 100_000)
    if not faltante or faltante != faltante or faltante < minimo:
        return None
    recompras = []
    if ranking is not None and not ranking.empty and {"senal", "dist_max_52s"} <= set(ranking.columns):
        for t in posiciones:
            if t in ranking.index and str(ranking.at[t, "senal"]) == "AGREGAR":
                d = _num(ranking.at[t, "dist_max_52s"])
                if d == d and d <= -0.10:
                    recompras.append(f"{t} ({d:.0%} desde su máximo, el análisis sigue positivo)")
    texto = f"Para ejecutar el plan completo faltan ${faltante:,.0f}."
    if recompras:
        texto += " Oportunidades de recompra: " + ", ".join(recompras) + "."
    return {"monto": faltante, "texto": texto, "recompras": recompras}
