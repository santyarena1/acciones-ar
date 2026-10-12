"""Operador automático: analiza, decide y ejecuta en el broker (paper o IOL real).

Ciclo (lo dispara la tarea programada varias veces por día hábil):
 1. ¿pausado? ¿mercado abierto? (si no, no opera)
 2. cancela órdenes que quedaron pendientes de ruedas anteriores (solo IOL)
 3. corre el análisis completo contra la cartera real del broker
 4. decide qué ejecutar (salidas y entradas siempre; ajustes solo si superan la banda)
 5. protecciones técnicas: sin repetidas, precio sano vs. cotización en vivo, compras ajustadas a la caja
 6. envía ventas y después compras, todo a precio límite; registra cada respuesta
 7. si falta plata para el plan, avisa cuánto y por qué (pedido de fondos)

Modo real: requiere `operador.modo: live` en settings Y `IOL_LIVE_TRADING=1` en el .env (lo activa el dueño).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import pandas as pd

from ..portfolio.risk import RiskError, limit_price, validate_orders
from .aportes import detectar_aporte
from .seguimiento import actualizar as actualizar_seguimiento
from .bitacora import Bitacora
from .decision import (ajustar_a_caja, ajustar_ventas, claves_operadas_hoy, filtrar_por_banda, laminas_de_cotizaciones,
                       pedido_de_fondos, precio_sano, sin_repetidas)
from .mercado import ahora_ar, feriados_ar, mercado_abierto
from .notificar import notificar


class ModoRealNoHabilitado(Exception):
    pass


@dataclass
class Resultado:
    estado: str                      # operó | sin_cambios | cerrado | pausado | error
    mensaje: str = ""
    enviadas: list[dict] = field(default_factory=list)
    pedido_fondos: dict | None = None
    corrida: str | None = None


def _broker(modo: str, settings: dict):
    from ..servicio import crear_broker

    if modo == "live":
        if os.getenv("IOL_LIVE_TRADING") != "1":
            raise ModoRealNoHabilitado("Modo real pedido pero IOL_LIVE_TRADING no es 1 en el .env.")
        return crear_broker("iol", settings)
    return crear_broker("paper", settings)


def _cancelar_viejas(broker, bit: Bitacora, hoy) -> None:
    for o in broker.open_orders() or []:
        fecha = str(o.get("fecha") or "")[:10]
        if fecha and fecha < hoy.isoformat():
            r = broker.cancel_order(o.get("numero"))
            bit.registrar("cancelacion", numero=o.get("numero"), simbolo=o.get("simbolo"), respuesta=r)


def _ya_operadas_hoy(broker, bit: Bitacora, hoy) -> set[tuple[str, str]]:
    """Lo que la bitácora registró hoy + lo que el broker muestra como operado hoy (por si se cortó el proceso)."""
    claves = bit.ordenes_del_dia(hoy)
    cliente = getattr(broker, "client", None)
    if cliente is not None:
        from ..broker.iol import parse_operaciones
        claves |= claves_operadas_hoy(parse_operaciones(cliente.operaciones(desde=hoy)), hoy)
    return claves


def _con_precio_vivo(ords: pd.DataFrame, broker, bit: Bitacora, cfg: dict, hoy) -> tuple[pd.DataFrame, dict]:
    """Compara cada orden con la cotización en vivo (punta compradora/vendedora). En real, sin cotización no opera."""
    exigir = broker.nombre == "iol"
    cotizaciones, filas = {}, []
    for _, o in ords.iterrows():
        q = broker.get_quote(o["ticker"])
        cotizaciones[o["ticker"]] = q
        ok, px = precio_sano(float(o["precio_ref"]), q, cfg.get("tolerancia_precio", 0.05), lado=o["lado"],
                             exigir=exigir, hoy=hoy)
        if not ok:
            bit.registrar("descartada", ticker=o["ticker"], lado=o["lado"], motivo="precio fuera de tolerancia o viejo",
                          precio_analisis=o["precio_ref"], precio_vivo=px)
            continue
        filas.append({**o.to_dict(), "precio_ref": px})
    out = pd.DataFrame(filas, columns=ords.columns) if filas else ords.iloc[0:0]
    return out, cotizaciones


def _preparar(c, broker, bit: Bitacora, settings: dict, hoy) -> tuple[pd.DataFrame, float]:
    cfg = settings.get("operador", {})
    posiciones = c.meta["cartera"]["posiciones"]
    ords = filtrar_por_banda(c.ordenes, posiciones, cfg.get("banda_no_operar", 0.02))
    ords = sin_repetidas(ords, _ya_operadas_hoy(broker, bit, hoy))
    ords, cotizaciones = _con_precio_vivo(ords, broker, bit, cfg, hoy)
    laminas = laminas_de_cotizaciones(cotizaciones)
    ords = ajustar_ventas(ords, posiciones, laminas)
    prioridad = c.ranking["score"].to_dict() if "score" in c.ranking else {}
    if not c.renta_fija.empty and "score_rf" in c.renta_fija:
        prioridad.update(c.renta_fija["score_rf"].dropna().to_dict())
    recargo = settings["riesgo"]["slippage_limite"] + settings.get("costos", {}).get("comision_bps", 50) / 1e4         + settings.get("costos", {}).get("derechos_bps", 8) / 1e4
    return ajustar_a_caja(ords, broker.get_cash_ars(), prioridad, recargo=recargo, laminas=laminas,
                          monto_minimo=settings["portfolio"]["orden_minima_ars"])


def _enviar(ords: pd.DataFrame, broker, bit: Bitacora, settings: dict) -> list[dict]:
    slip = settings["riesgo"]["slippage_limite"]
    enviadas = []
    for _, o in ords.sort_values("lado", ascending=False).iterrows():   # VENDER antes que COMPRAR
        mult = float(o.get("mult", 1.0) or 1.0)
        px = limit_price(o["lado"], float(o["precio_ref"]), slip)
        extra = {"tipo": "bono"} if broker.nombre == "paper" and mult != 1.0 else {}
        bit.registrar_intento(o["ticker"], o["lado"], cantidad=int(o["cantidad"]), precio=px, mult=mult)
        try:
            r = broker.place_order(o["ticker"], o["lado"], int(o["cantidad"]), px, mult=mult, **extra)
        except Exception as e:  # el broker puede fallar a mitad de camino: se registra y sigue
            r = {"estado": "error", "mensaje": str(e)}
        ev = bit.registrar("orden", ticker=o["ticker"], lado=o["lado"], cantidad=int(o["cantidad"]), precio=px,
                           mult=mult, motivo=o.get("motivo"), estado=r.get("estado"), id=r.get("id"),
                           mensaje=r.get("mensaje"))
        enviadas.append(ev)
    return enviadas


def _validar_tecnico(ords: pd.DataFrame, valor_total: float, settings: dict) -> None:
    """Chequeo anti-bug: ninguna orden puede ser más grande que una fracción absurda de la cartera."""
    tope = settings["riesgo"].get("orden_maxima_pct_cartera", 0.35) * valor_total
    for _, o in ords.iterrows():
        monto = int(o["cantidad"]) * float(o["precio_ref"]) * float(o.get("mult", 1.0) or 1.0)
        if valor_total > 0 and monto > tope:
            raise RiskError(f"Orden de {o['ticker']} por ${monto:,.0f} supera el {tope / valor_total:.0%} de la cartera: "
                            "parece un dato roto, no se envía nada.")


def _ventas_por_acreditar(bit: Bitacora, desde_ts: str | None) -> float:
    """Montos vendidos desde la foto anterior de caja, contando 1 día hábil extra por la liquidación T+1."""
    if not desde_ts:
        return 0.0
    from datetime import datetime, timedelta
    corte = (datetime.fromisoformat(desde_ts) - timedelta(days=3)).isoformat()   # cubre fin de semana
    total = 0.0
    for ev in bit.eventos(tipo="orden"):
        if ev.get("lado") == "VENDER" and ev.get("estado") not in ("rechazada", "error") and ev["ts"] >= corte:
            total += float(ev.get("cantidad", 0)) * float(ev.get("precio", 0)) * float(ev.get("mult", 1) or 1)
    return total


def _registrar_aportes(bit: Bitacora, modo: str, broker, valor_total: float) -> float:
    """Detecta depósitos/retiros desde la corrida anterior y lleva la cuenta de lo que puso el dueño."""
    est = (bit.estado().get("aportes") or {}).get(modo) or {}
    caja = broker.get_cash_ars()
    if "total" not in est:                       # primera vez: todo lo que hay es capital aportado
        bit.registrar("aporte", modo=modo, monto=round(valor_total, 0), inicial=True)
        return valor_total, 0.0
    ventas = 0.0 if broker.nombre == "paper" else _ventas_por_acreditar(bit, est.get("caja_ts"))
    aporte = detectar_aporte(est.get("caja"), caja, ventas, 0.0, valor_total)
    if aporte:
        bit.registrar("aporte", modo=modo, monto=aporte)
        verbo = "ingresaste" if aporte > 0 else "retiraste"
        notificar("Movimiento de fondos", f"Detecté que {verbo} ${abs(aporte):,.0f}. "
                  + ("Lo voy a invertir según el plan." if aporte > 0 else "Ajusto la cartera a lo que queda."))
    return float(est["total"]) + aporte, aporte


def _precios_benchmark(c) -> dict[str, float]:
    """SPY (CEDEAR, en pesos) y Merval (en pesos) para comparar contra no hacer nada."""
    out = {}
    if "SPY" in c.ranking.index and c.ranking.at["SPY", "precio_ars"] == c.ranking.at["SPY", "precio_ars"]:
        out["SPY"] = float(c.ranking.at["SPY", "precio_ars"])
    try:
        from datetime import date, timedelta
        from ..data.prices import load_many
        m = load_many(["^MERV"], date.today() - timedelta(days=10)).get("^MERV")
        if m is not None and not m.empty:
            out["MERV"] = float(m["close"].iloc[-1])
    except Exception:  # sin Merval se compara solo contra el S&P 500
        pass
    return out


def _seguir(bit: Bitacora, modo: str, c, aporte: float, settings: dict) -> None:
    seg = bit.estado().get("seguimiento") or {}
    umbral = settings.get("operador", {}).get("aviso_caida", -0.15)
    nuevo, aviso = actualizar_seguimiento(seg.get(modo), float(c.meta["cartera"]["valor_total"]), aporte,
                                          _precios_benchmark(c), umbral)
    seg[modo] = nuevo
    bit.guardar_estado(seguimiento=seg)
    bit.registrar("foto", modo=modo, valor=nuevo["valor"], indice=round(nuevo["indice"], 6),
                  bm_indice=round(nuevo.get("bm_indice", 1.0), 6))
    if aviso:
        bit.registrar("aviso_caida", modo=modo, texto=aviso)
        notificar("Aviso: caída fuerte", aviso)


def _guardar_aportes(bit: Bitacora, modo: str, total: float, broker) -> None:
    from .bitacora import ahora_iso
    aportes = bit.estado().get("aportes") or {}
    aportes[modo] = {"total": round(total, 0), "caja": broker.get_cash_ars(), "caja_ts": ahora_iso()}
    bit.guardar_estado(aportes=aportes)


def operar(settings: dict, universe: list[dict], modo: str | None = None, forzar_horario: bool = False,
           bitacora: Bitacora | None = None) -> Resultado:
    from ..servicio import correr

    cfg = settings.get("operador", {})
    modo = modo or cfg.get("modo", "paper")
    bit = bitacora or Bitacora()
    if bit.estado().get("pausado"):
        bit.registrar("salteo", motivo="operador pausado")
        return Resultado("pausado", "El operador está pausado.")
    ahora = ahora_ar()
    if not forzar_horario and not mercado_abierto(ahora, feriados_ar()):
        return Resultado("cerrado", "Mercado cerrado: no se opera.")
    try:
        with bit.candado():
            broker = _broker(modo, settings)
            _cancelar_viejas(broker, bit, ahora.date())
            c = correr(cfg.get("horizonte", settings["horizonte_default"]),
                       cfg.get("perfil", settings["perfil_default"]), broker.nombre, settings, universe, broker=broker)
            aportes, aporte = _registrar_aportes(bit, modo, broker, float(c.meta["cartera"]["valor_total"]))
            _seguir(bit, modo, c, aporte, settings)
            ords, faltante = _preparar(c, broker, bit, settings, ahora.date())
            cartera = c.meta["cartera"]
            _validar_tecnico(ords, float(cartera["valor_total"]), settings)
            if not ords.empty:
                ords = validate_orders(ords, settings, cartera["posiciones"], broker.get_cash_ars(),
                                       valor_total=float(cartera["valor_total"]))
            enviadas = _enviar(ords, broker, bit, settings)
            _guardar_aportes(bit, modo, aportes, broker)          # foto de la caja después de operar
    except Exception as e:
        bit.registrar("error", modo=modo, error=f"{type(e).__name__}: {e}")
        notificar("Operador: error", f"{type(e).__name__}: {e}")
        return Resultado("error", f"{type(e).__name__}: {e}")
    pedido = pedido_de_fondos(faltante, c.ranking, c.meta["cartera"]["posiciones"], settings)
    return _cerrar(bit, modo, c, enviadas, pedido)


def _cerrar(bit: Bitacora, modo: str, c, enviadas: list[dict], pedido: dict | None) -> Resultado:
    bit.registrar("corrida", modo=modo, corrida=c.stamp, ordenes=len(enviadas),
                  regimen=c.meta["macro"].get("regimen"), valor_total=c.meta["cartera"]["valor_total"])
    bit.guardar_estado(ultimo_pedido_fondos=pedido)      # si ya no hace falta plata, el aviso se borra
    if pedido:
        bit.registrar("pedido_fondos", **pedido)
        notificar("El operador pide fondos", pedido["texto"])
    if enviadas:
        bit.guardar_estado(ultimo_rebalanceo=c.stamp)
        resumen = ", ".join(f"{e['lado'][0]} {e['cantidad']} {e['ticker']}" for e in enviadas[:6])
        notificar(f"Operador ({modo}): {len(enviadas)} órdenes", resumen)
        return Resultado("operó", resumen, enviadas, pedido, c.stamp)
    return Resultado("sin_cambios", "Cartera alineada: no hacía falta operar.", [], pedido, c.stamp)
