"""Bitácora y estado del operador en la base (Postgres en la nube). Misma interfaz que `Bitacora`.

- eventos: una fila por evento (tipo y modo en columnas, el resto en `datos`). Al leer se rearma el mismo dict
  que la versión en archivos: {"ts": ISO en hora Argentina, "tipo", "modo"?, **datos}.
- estado: una fila por clave. 'pausado' = {pausado, motivo} (en el dict del operador: pausado + motivo_pausa);
  el resto de las claves (aportes, seguimiento, ultimo_pedido_fondos, ultimo_rebalanceo, modo_real,
  ultimo_resumen_diario) van tal cual. 'candado' = {pid, ts, corrida} es el candado entre corridas.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from .. import db
from ..broker.iol import tz_argentina
from .bitacora import CANDADO_VENCE_SEG, Bitacora, OperadorOcupado, ahora_iso

log = logging.getLogger(__name__)
CLAVES_PAUSA = ("pausado", "motivo_pausa")


def _limpio(o):
    """Lo que viaja a jsonb: sin NaN/inf, sin tipos de numpy/pandas, sin NUL (Postgres no los acepta)."""
    from ..store import limpiar_json
    return limpiar_json(o)


class BitacoraDB(Bitacora):
    def __init__(self, engine=None):          # noqa: D401 - no usa carpetas
        self.engine = engine

    # --- eventos ------------------------------------------------------------
    def registrar(self, tipo: str, **datos) -> dict:
        ts = ahora_iso()
        ev = {"ts": ts, "tipo": tipo, **datos}
        resto = {k: v for k, v in datos.items() if k != "modo"}
        db.insertar_evento(tipo, datos.get("modo"), _limpio(resto), datetime.fromisoformat(ts), self.engine)
        return ev

    def eventos(self, ultimos: int | None = None, tipo: str | None = None, desde: str | None = None,
                tipos: tuple[str, ...] | None = None) -> list[dict]:
        filtro = (tipo,) if tipo is not None else tipos
        corte = datetime.fromisoformat(desde) if desde else None
        filas = db.consultar_eventos(filtro, corte, ultimos, self.engine)
        return [_a_evento(f) for f in filas]

    # --- estado -------------------------------------------------------------
    def estado(self) -> dict:
        """Estado armado desde las filas. Una fila de pausa rota deja el operador PAUSADO (falla cerrado)."""
        filas = db.kv_todos("estado", self.engine)
        out: dict = {"pausado": False, "ultimo_rebalanceo": None}
        for clave, valor in filas.items():
            if clave == "candado":
                continue
            if clave == "pausado":
                out.update(_pausa(valor))
            else:
                out[clave] = valor
        return out

    def guardar_estado(self, **cambios) -> dict:
        nuevo = {**self.estado(), **cambios}
        filas = {k: _limpio(v) for k, v in cambios.items() if k not in CLAVES_PAUSA}
        if any(k in cambios for k in CLAVES_PAUSA):
            filas["pausado"] = {"pausado": bool(nuevo.get("pausado")), "motivo": nuevo.get("motivo_pausa")}
        if filas:
            db.kv_set_varios("estado", filas, self.engine)
        return nuevo

    # --- candado ------------------------------------------------------------
    @contextmanager
    def candado(self, vence_seg: float = CANDADO_VENCE_SEG) -> Iterator[None]:
        info = {"pid": os.getpid(), "ts": ahora_iso(), "corrida": os.getenv("GITHUB_RUN_ID")}
        marca, reemplazo = db.tomar_candado(info, vence_seg, self.engine)
        if marca is None:
            raise OperadorOcupado("otra corrida del operador está en curso")
        if reemplazo:
            self.registrar("aviso", mensaje="candado abandonado de una corrida anterior: se reemplaza")
        try:
            yield
        finally:
            db.soltar_candado(marca, self.engine)


def _pausa(valor) -> dict:
    if not isinstance(valor, dict) or not isinstance(valor.get("pausado"), bool):
        log.error("estado 'pausado' ilegible: el operador queda pausado")
        return {"pausado": True, "motivo_pausa": "estado de pausa ilegible"}
    return {"pausado": valor["pausado"], "motivo_pausa": valor.get("motivo")}


def _a_evento(fila: dict) -> dict:
    ts = fila["ts"].astimezone(tz_argentina()).isoformat(timespec="seconds")
    datos = fila.get("datos") if isinstance(fila.get("datos"), dict) else {}
    base = {"ts": ts, "tipo": fila["tipo"]}
    if fila.get("modo") is not None:
        base["modo"] = fila["modo"]
    return {**datos, **base}
