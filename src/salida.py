"""Modo silencioso para la nube (SALIDA_SILENCIOSA=1).

El repo es público y los logs de GitHub Actions también: en ese modo la CLI imprime solo líneas de estado
genéricas ("[ok] corrida guardada; 3 órdenes"), nunca montos, tickers, posiciones, saldos, credenciales ni
mensajes de excepciones. Todo lo demás (prints, logging, warnings, stderr) se descarta; el detalle completo queda
en la bitácora de la base (tabla eventos), que es privada.
"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Iterator

ENV = "SALIDA_SILENCIOSA"
_REAL: list = []          # stdout original mientras dura el silencio


class _Nulo:
    """Destino que descarta todo (no acumula memoria)."""
    encoding = "utf-8"

    def write(self, texto: str) -> int:
        return len(texto)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def silenciosa() -> bool:
    return os.getenv(ENV, "").strip() == "1"


@contextmanager
def silenciar() -> Iterator[None]:
    """En modo silencioso descarta stdout, stderr y logging dentro del bloque. Si no, no hace nada."""
    if not silenciosa():
        yield
        return
    nivel_previo = logging.root.manager.disable
    _REAL.append(sys.stdout)
    logging.disable(logging.CRITICAL)
    try:
        with redirect_stdout(_Nulo()), redirect_stderr(_Nulo()):
            yield
    finally:
        logging.disable(nivel_previo)
        _REAL.pop()


def estado(linea: str) -> None:
    """Línea de estado que SIEMPRE se ve (aun en silencio). Solo texto genérico: nada sensible."""
    destino = _REAL[-1] if _REAL else sys.stdout
    print(linea, file=destino, flush=True)


def linea_operar(estado_corrida: str, ordenes: int, hay_pedido: bool) -> str:
    """Resumen genérico de una corrida del operador (sin montos ni tickers)."""
    lineas = {
        "operó": f"[ok] corrida guardada; {ordenes} órdenes",
        "sin_cambios": "[ok] corrida guardada; sin órdenes",
        "analizado": "[ok] análisis guardado; mercado cerrado, sin órdenes",
        "cerrado": "[ok] mercado cerrado; no se corrió",
        "pausado": "[ok] operador pausado; no se corrió",
        "ocupado": "[ok] otra corrida en curso; no se corrió",
        "error": "[error] la corrida falló (detalle en la bitácora)",
    }
    linea = lineas.get(estado_corrida, "[ok] corrida terminada")
    return linea + ("; hay un pedido de fondos" if hay_pedido else "")
