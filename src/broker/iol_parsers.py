"""Parsers puros de las respuestas de la API v2 de IOL (testeables sin red).

Los campos se parsean de forma defensiva: si IOL cambia nombres, ajustar acá y en tests/test_iol_parsers.py
(fixtures en tests/fixtures/iol_*.json).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

# Plazo de la orden -> clave de liquidación en estadocuenta.cuentas[].saldos[]
PLAZO_A_LIQUIDACION = {"t0": "inmediato", "t1": "hrs24", "t2": "hrs48", "t3": "hrs72"}


# --- parsers (testeables sin red) ----------------------------------------
def _f(v: Any) -> float | None:
    """float defensivo: None/'' -> None; strings con coma decimal también."""
    if v is None or v == "" or isinstance(v, (dict, list, bool)):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _f0(v: Any) -> float:
    x = _f(v)
    return 0.0 if x is None else x


def parse_history(raw) -> pd.DataFrame:
    filas = []
    for it in raw or []:
        fecha = it.get("fechaHora") or it.get("fecha")
        cierre = it.get("ultimoPrecio", it.get("cierre"))
        if fecha is None or cierre is None:
            continue
        filas.append({
            "date": pd.to_datetime(str(fecha)[:10]),
            "close": float(cierre),
            "volume": float(it.get("volumenNominal", it.get("volumen", 0)) or 0),
        })
    if not filas:
        return pd.DataFrame(columns=["close", "volume"])
    df = pd.DataFrame(filas).groupby("date").last().sort_index()
    return df[df["close"] > 0]


# Mapeo titulo.tipo de IOL (en minúsculas, por substring) -> clase interna. Se evalúa en orden.
# IOL manda el tipo con mayúsculas variables ('ACCIONES', 'aCCIONES', 'CEDEARS', 'TitulosPublicos',
# 'Letras', 'ObligacionesNegociables', ...). Los soberanos USD (GD/AL), CER y duales vienen como
# TitulosPublicos -> 'bono'. Las LECAP vienen como Letras -> 'letra'; las BONCAP suelen figurar como
# TitulosPublicos -> 'bono' (verificar con una tenencia real).
_EXCLUIR_TIPOS = ("suscrib", "cupon", "fondo", "fci", "caucion", "opcion", "futuro", "cheque",
                  "indice", "divisa", "certificado", "fideicomiso", "componente")
_MAPA_TIPOS: tuple[tuple[str, str], ...] = (
    ("cedear", "cedear"),
    ("accion", "accion"),
    ("obligaciones", "on"),        # obligacionesNegociables, oBLIGACIONESPYME
    ("letra", "letra"),            # letras, letraNota, lETRASDEPRECADO
    ("letes", "letra"),
    ("titulospublicos", "bono"),
    ("titulosdeuda", "bono"),
    ("bono", "bono"),              # bONOS, bONEX, bODEN
    ("bocon", "bono"),
    ("boden", "bono"),
    ("rentafija", "bono"),
)
# Bonos, letras y ONs cotizan cada 100 VN: monto = cantidad (VN) * precio * 0.01.
MULT_PRECIO = {"accion": 1.0, "cedear": 1.0, "bono": 0.01, "letra": 0.01, "on": 0.01}


def clasificar_tipo(tipo: str | None) -> str | None:
    """'accion' | 'cedear' | 'bono' | 'letra' | 'on' | None (FCI, cauciones, opciones, etc. afuera).

    Sin tipo, se asume acción (compatibilidad con respuestas viejas).
    """
    t = (tipo or "").lower()
    if not t:
        return "accion"
    if any(x in t for x in _EXCLUIR_TIPOS):
        return None
    for clave, clase in _MAPA_TIPOS:
        if clave in t:
            return clase
    return None


def multiplicador_precio(tipo: str | None) -> float:
    """Factor para pasar precio de pantalla a pesos por unidad (0.01 para bonos/letras/ONs)."""
    return MULT_PRECIO.get(tipo or "accion", 1.0)


def _moneda(titulo: dict, activo: dict) -> str:
    m = str(titulo.get("moneda") or activo.get("moneda") or "").lower()
    return "USD" if "dolar" in m else "ARS"


def _precio_por_100(cantidad: int, precio: float, ppc: float | None,
                    valorizado: float | None) -> tuple[float, float | None, bool]:
    """Renta fija: IOL debería dar el precio cada 100 VN (valorizado = cantidad * precio / 100). Si el valorizado
    indica que vino por unidad (valorizado ~ cantidad * precio), se pasa a cada 100 VN. Devuelve
    (precio, ppc, unidad_dudosa)."""
    if not valorizado or precio <= 0 or cantidad <= 0:
        return precio, ppc, False
    ratio = valorizado / (cantidad * precio)
    if 0.005 <= ratio <= 0.02:          # cada 100 VN (lo esperado)
        return precio, ppc, False
    if 0.5 <= ratio <= 2.0:             # por unidad de VN -> x100
        return precio * 100, (ppc * 100 if ppc is not None else None), False
    return precio, ppc, True


def _posicion(a: dict, titulo: dict, clase: str, cantidad: int) -> dict:
    precio, ppc, valorizado = _f0(a.get("ultimoPrecio")), _f(a.get("ppc")), _f(a.get("valorizado"))
    dudosa = False
    if MULT_PRECIO.get(clase, 1.0) != 1.0:
        precio, ppc, dudosa = _precio_por_100(cantidad, precio, ppc, valorizado)
    comprometido = int(_f0(a.get("comprometido")))
    return {
        "cantidad": cantidad, "precio": precio, "ppc": ppc, "valorizado": valorizado, "tipo": clase,
        "moneda": _moneda(titulo, a), "comprometido": comprometido,
        "disponible": max(0, cantidad - comprometido), "unidad_dudosa": dudosa,
    }


def parse_positions(raw) -> dict[str, dict]:
    """Portafolio -> {ticker: {cantidad, precio, ppc, valorizado, tipo, moneda, comprometido, disponible,
    unidad_dudosa}}.

    Incluye acciones, CEDEARs, bonos, letras y ONs (ver `clasificar_tipo`). Para renta fija IOL informa
    `cantidad` en valor nominal (VN) y `ultimoPrecio`/`ppc` cada 100 VN; `valorizado` ya viene en moneda
    (cantidad * precio / 100). Usar `multiplicador_precio(tipo)` para calcular montos.
    OJO: `moneda` = "USD" significa que precio/ppc/valorizado están en DÓLARES (pasa con algunas ONs): hay que
    convertirlos antes de sumarlos a pesos. `disponible` = cantidad - comprometido (lo que se puede vender:
    lo comprometido ya está en otra orden de venta).
    """
    out: dict[str, dict] = {}
    for a in (raw or {}).get("activos", []) or []:
        titulo = a.get("titulo") or {}
        simbolo = titulo.get("simbolo") or a.get("simbolo")
        clase = clasificar_tipo(titulo.get("tipo") or a.get("tipo"))
        if not simbolo or clase is None:
            continue
        cantidad = int(_f0(a.get("cantidad")))
        if cantidad <= 0:
            continue
        out[simbolo] = _posicion(a, titulo, clase, cantidad)
    return out


def _cuenta_pesos(raw) -> dict | None:
    cuentas = [c for c in (raw or {}).get("cuentas", []) or []
               if "peso" in str(c.get("moneda", "")).lower()]
    if not cuentas:
        return None
    # Preferir la cuenta de inversión propia sobre la administrada.
    for c in cuentas:
        if str(c.get("tipo", "")).lower().startswith("inversion"):
            return c
    return cuentas[0]


def parse_cash_ars(raw, plazo: str | None = None) -> float:
    """Pesos disponibles para operar (nunca negativo).

    Sin plazo: `disponible` de la cuenta en pesos. Con plazo (t0..t3) y si la respuesta trae
    `saldos[]` por liquidación, usa el menor entre `disponibleOperar` y `disponible` del saldo de ese plazo
    (t1 -> 'hrs24'), que es lo que realmente se puede usar sin tomar descubierto.
    """
    cuenta = _cuenta_pesos(raw)
    if cuenta is None:
        return 0.0
    liquidacion = PLAZO_A_LIQUIDACION.get(plazo or "")
    if liquidacion:
        for s in cuenta.get("saldos", []) or []:
            if s.get("liquidacion") == liquidacion:
                # el menor de los dos: si uno incluye descubierto/margen, no lo usamos para comprar
                valores = [v for v in (_f(s.get("disponibleOperar")), _f(s.get("disponible"))) if v is not None]
                if valores:
                    return max(0.0, min(valores))
    return max(0.0, _f0(cuenta.get("disponible")))


def _mejores_puntas(puntas: Any) -> dict[str, float | None]:
    lista = puntas if isinstance(puntas, list) else ([puntas] if isinstance(puntas, dict) else [])
    compras = [(_f(p.get("precioCompra")), _f(p.get("cantidadCompra"))) for p in lista]
    ventas = [(_f(p.get("precioVenta")), _f(p.get("cantidadVenta"))) for p in lista]
    compras = [c for c in compras if c[0] and c[0] > 0]
    ventas = [v for v in ventas if v[0] and v[0] > 0]
    bid = max(compras, key=lambda x: x[0]) if compras else (None, None)
    ask = min(ventas, key=lambda x: x[0]) if ventas else (None, None)
    return {"precioCompra": bid[0], "cantidadCompra": bid[1], "precioVenta": ask[0], "cantidadVenta": ask[1]}


def parse_quote(raw) -> dict | None:
    """Cotización -> {ultimoPrecio, precioCompra, cantidadCompra, precioVenta, cantidadVenta,
    volumen, montoOperado, cierreAnterior, fecha, laminaMinima, lote}. None si no hay último precio."""
    if not isinstance(raw, dict):
        return None
    ultimo = _f(raw.get("ultimoPrecio"))
    if ultimo is None:
        return None
    return {
        "ultimoPrecio": ultimo,
        **_mejores_puntas(raw.get("puntas")),
        "volumen": _f(raw.get("volumenNominal", raw.get("volumen"))),
        "montoOperado": _f(raw.get("montoOperado")),
        "cierreAnterior": _f(raw.get("cierreAnterior", raw.get("ultimoCierre"))),
        "fecha": raw.get("fechaHora") or raw.get("fecha"),
        "laminaMinima": _f(raw.get("laminaMinima")),
        "lote": _f(raw.get("lote")),
    }


def parse_panel(raw) -> list[dict]:
    """Panel / 'Todos' -> [{simbolo, ultimoPrecio, volumen, montoOperado, descripcion}]."""
    titulos = raw.get("titulos", []) if isinstance(raw, dict) else (raw or [])
    out = []
    for t in titulos or []:
        simbolo = t.get("simbolo")
        if not simbolo:
            continue
        out.append({
            "simbolo": simbolo,
            "ultimoPrecio": _f(t.get("ultimoPrecio")),
            "volumen": _f(t.get("volumen", t.get("volumenNominal"))),
            "montoOperado": _f(t.get("montoOperado")),
            "descripcion": t.get("descripcion"),
        })
    return out


def _operacion(o: dict) -> dict | None:
    numero = o.get("numero", o.get("numeroOperacion"))
    try:
        numero = int(numero)
    except (TypeError, ValueError):
        return None
    monto = o.get("montoOperado")
    if monto is None:
        monto = o.get("montoOperacion")
    return {
        "numero": numero,
        "fecha": o.get("fechaOrden") or o.get("fechaAlta") or o.get("fecha"),
        "simbolo": o.get("simbolo"),
        "tipo": (str(o["tipo"]).lower() if o.get("tipo") else None),
        "estado": o.get("estado") or o.get("estadoActual"),
        "cantidad": _f(o.get("cantidad")),
        "precio": _f(o.get("precio")),
        "montoOperado": _f(monto),
    }


def parse_operaciones(raw) -> list[dict]:
    """Lista (o detalle suelto) de operaciones -> [{numero, fecha, simbolo, tipo, estado,
    cantidad, precio, montoOperado}]."""
    items = [raw] if isinstance(raw, dict) else (raw or [])
    return [op for op in (_operacion(o) for o in items if isinstance(o, dict)) if op is not None]


def _mensajes(raw: dict) -> str:
    partes = []
    for m in raw.get("messages") or []:
        if isinstance(m, dict):
            texto = ": ".join(x for x in (m.get("title"), m.get("description")) if x)
        else:
            texto = str(m)
        if texto:
            partes.append(texto)
    return " | ".join(partes)


def parse_order_response(raw) -> dict:
    """Respuesta de operar/Comprar|Vender o de DELETE operaciones -> {estado, id, mensaje}.

    estado: 'enviada' (ok o con número), 'rechazada' (ok: false), 'incierta' (2xx ambiguo) o 'desconocido'."""
    if not isinstance(raw, dict):
        return {"estado": "desconocido", "id": None, "mensaje": f"Respuesta inesperada de IOL: {raw!r}"[:300]}
    numero = raw.get("numeroOperacion")
    ok = raw.get("ok")
    if ok is True or (ok is None and numero is not None):
        estado, defecto = "enviada", "Orden aceptada por IOL."
    elif ok is False:
        estado, defecto = "rechazada", "IOL rechazó la orden."
    else:  # 2xx sin 'ok' ni número: no sabemos si entró -> no reenviar sin revisar
        estado, defecto = "incierta", "Respuesta de IOL sin confirmación: revisá las operaciones antes de reenviar."
    return {"estado": estado, "id": numero, "mensaje": _mensajes(raw) or defecto}


def resumen_estadocuenta(raw) -> dict:
    """Estructura de saldos para diagnosticar la lectura de caja (sin números de cuenta ni datos personales).
    Se guarda en la base privada, nunca en logs públicos."""
    campos = ("disponible", "comprometido", "saldo", "titulosValorizados", "total", "margenDescubierto")
    cuentas = []
    for c in (raw or {}).get("cuentas", []) or []:
        cuentas.append({
            "tipo": c.get("tipo"), "moneda": c.get("moneda"), "estado": c.get("estado"),
            **{k: c.get(k) for k in campos if k in c},
            "saldos": [{k: s.get(k) for k in ("liquidacion", "saldo", "comprometido", "disponible",
                                              "disponibleOperar") if k in s} for s in c.get("saldos", []) or []],
        })
    return {"claves_raiz": sorted((raw or {}).keys()), "totalEnPesos": (raw or {}).get("totalEnPesos"),
            "cuentas": cuentas}


def resumen_portafolio(raw) -> dict:
    activos = (raw or {}).get("activos", []) or []
    return {"claves_raiz": sorted((raw or {}).keys()), "cantidad_activos": len(activos),
            "tipos": sorted({str((a.get("titulo") or {}).get("tipo")) for a in activos}),
            "claves_activo": sorted(activos[0].keys()) if activos else []}
