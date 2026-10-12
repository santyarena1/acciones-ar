"""Resumen diario por Telegram: una vez por día hábil, en la última corrida (~16:30 hora Argentina).

Cuenta: valor de la cartera, ganancia real (sin contar depósitos), comparación contra no hacer nada, operaciones
del día y si hay un pedido de fondos. No se repite: estado 'ultimo_resumen_diario' = fecha (AAAA-MM-DD).
"""
from __future__ import annotations

from datetime import date, datetime, time

from .aportes import rendimiento
from .bitacora import inicio_del_dia
from .mercado import es_habil
from .notificar import notificar
from .seguimiento import resumen as resumen_seguimiento

HORA_RESUMEN = time(16, 25)
MAX_OPERACIONES = 8
ESTADOS_FALLIDOS = ("rechazada", "error")
NOMBRE_MODO = {"paper": "práctica", "live": "real"}


def plata(x: float) -> str:
    return f"${x:,.0f}".replace(",", ".")


def pct(x: float) -> str:
    return f"{x:+.1%}".replace(".", ",")


def corresponde(ahora: datetime, feriados: set[date], estado: dict) -> bool:
    """`ahora` naive en hora Argentina."""
    return (es_habil(ahora.date(), feriados) and ahora.time() >= HORA_RESUMEN
            and estado.get("ultimo_resumen_diario") != ahora.date().isoformat())


def _linea_operacion(ev: dict) -> str:
    verbo = "Compró" if ev.get("lado") == "COMPRAR" else "Vendió"
    return f"- {verbo} {ev.get('cantidad')} {ev.get('ticker')} a {plata(float(ev.get('precio') or 0))}"


def _lineas_rendimiento(estado: dict, modo: str) -> list[str]:
    seg = (estado.get("seguimiento") or {}).get(modo) or {}
    aportes = ((estado.get("aportes") or {}).get(modo) or {}).get("total")
    if not seg.get("valor"):
        return ["Todavía no hay una foto de la cartera."]
    lineas = [f"Valor de la cartera: {plata(seg['valor'])}"]
    ganancia, g_pct = rendimiento(float(seg["valor"]), float(aportes or 0))
    if g_pct is not None:
        lineas.append(f"Ganancia real (sin contar tus depósitos): {plata(ganancia)} ({pct(g_pct)})")
    r = resumen_seguimiento(seg)
    lineas.append(f"Operador {pct(r['operador'])} vs. no hacer nada {pct(r['no_hacer_nada'])}")
    return lineas


def armar(estado: dict, ordenes_hoy: list[dict], modo: str) -> str:
    """Texto del resumen (puro)."""
    ok = [e for e in ordenes_hoy if e.get("modo") in (modo, None) and e.get("estado") not in ESTADOS_FALLIDOS]
    lineas = [f"Modo {NOMBRE_MODO.get(modo, modo)}.", *_lineas_rendimiento(estado, modo)]
    lineas.append(f"Operaciones de hoy: {len(ok)}" if ok else "Hoy no hubo operaciones.")
    lineas += [_linea_operacion(e) for e in ok[:MAX_OPERACIONES]]
    if len(ok) > MAX_OPERACIONES:
        lineas.append(f"... y {len(ok) - MAX_OPERACIONES} más.")
    pedido = estado.get("ultimo_pedido_fondos")
    if isinstance(pedido, dict) and pedido.get("texto"):
        lineas.append(f"Pedido de fondos: {pedido['texto']}")
    return "\n".join(lineas)


def enviar_si_corresponde(bit, modo: str, ahora: datetime, feriados: set[date]) -> bool:
    """Manda el resumen si es la hora y todavía no salió hoy. Devuelve True si lo armó (y marcó el día)."""
    estado = bit.estado()
    if not corresponde(ahora, feriados, estado):
        return False
    ordenes = bit.eventos(tipo="orden", desde=inicio_del_dia(ahora.date()))
    enviado = notificar("Resumen del día", armar(estado, ordenes, modo))
    bit.guardar_estado(ultimo_resumen_diario=ahora.date().isoformat())
    bit.registrar("resumen_diario", modo=modo, enviado=enviado)
    return True
