"""Pedidos de la web al motor (tabla `comandos`). Se procesan al empezar cada corrida, dentro del candado.

- 'depositar_practica' {monto}: suma plata a la cartera de práctica (la corrida lo detecta como aporte).
- 'reiniciar_practica' {capital}: borra la cartera de práctica y arranca de cero (también su seguimiento).
- 'revisar' {}: marca nada más; la corrida en sí es la revisión.

Cada pedido se marca procesado ANTES de ejecutarlo (a lo sumo una vez) y después se guarda el resultado:
{ok: true, ...} o {ok: false, error: "texto para el dueño"}.
"""
from __future__ import annotations

import math

from .. import db

TIPOS = ("depositar_practica", "reiniciar_practica", "revisar")


class PedidoInvalido(ValueError):
    pass


def _numero(valor, nombre: str, permitir_cero: bool) -> float:
    if isinstance(valor, bool) or valor is None:
        raise PedidoInvalido(f"Falta {nombre} o no es un número.")
    try:
        x = float(valor)
    except (TypeError, ValueError):
        raise PedidoInvalido(f"{nombre.capitalize()} no es un número.") from None
    if not math.isfinite(x) or x < 0 or (x == 0 and not permitir_cero):
        raise PedidoInvalido(f"{nombre.capitalize()} tiene que ser mayor a cero.")
    return x


def _paper(settings: dict):
    from ..servicio import crear_broker
    return crear_broker("paper", settings)


def _reiniciar(bit, settings: dict, capital: float) -> None:
    _paper(settings).reiniciar(capital)
    est = bit.estado()
    cambios = {clave: {k: v for k, v in (est.get(clave) or {}).items() if k != "paper"}
               for clave in ("aportes", "seguimiento")}
    if (settings.get("operador") or {}).get("modo", "paper") == "paper":
        cambios["ultimo_pedido_fondos"] = None
    bit.guardar_estado(**cambios)


def ejecutar(tipo: str, datos: dict, bit, settings: dict) -> dict:
    datos = datos if isinstance(datos, dict) else {}
    try:
        if tipo == "depositar_practica":
            monto = _numero(datos.get("monto"), "el monto", permitir_cero=False)
            return {"ok": True, "monto": monto, "caja": _paper(settings).depositar(monto)}
        if tipo == "reiniciar_practica":
            capital = _numero(datos.get("capital"), "el capital", permitir_cero=True)
            _reiniciar(bit, settings, capital)
            return {"ok": True, "capital": capital}
        if tipo == "revisar":
            return {"ok": True}
        return {"ok": False, "error": "Pedido desconocido."}
    except (PedidoInvalido, ValueError) as e:
        return {"ok": False, "error": str(e)}


def procesar_comandos(bit, settings: dict, engine=None) -> list[dict]:
    """Procesa los pedidos pendientes en orden. Sin base de datos no hay pedidos."""
    if engine is None and not db.hay_db():
        return []
    hechos = []
    for cmd in db.comandos_pendientes(engine):
        if not db.reclamar_comando(cmd["id"], engine):
            continue
        try:
            resultado = ejecutar(cmd["tipo"], cmd.get("datos"), bit, settings)
        except Exception as e:  # noqa: BLE001 - un pedido roto no frena la corrida; queda registrado
            resultado = {"ok": False, "error": f"Falló al procesarlo ({type(e).__name__})."}
        db.resultado_comando(cmd["id"], resultado, engine)
        bit.registrar("comando", modo="paper" if cmd["tipo"] != "revisar" else None, comando=cmd["tipo"],
                      id_comando=cmd["id"], resultado=resultado)
        hechos.append({"id": cmd["id"], "tipo": cmd["tipo"], **resultado})
    return hechos
