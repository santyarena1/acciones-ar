"""Bitácora y estado del operador automático (data/operador/).

- bitacora.jsonl: un evento por línea (corridas, órdenes, respuestas del broker, avisos, errores). Nunca se borra.
- estado.json: pausado, modo, fecha del último rebalanceo, último aviso de fondos.
- operador.lock: candado para que dos corridas (tarea programada + manual) no operen a la vez.

Los timestamps van en hora Argentina (con offset) para que "el día" sea el día de BYMA aunque la PC esté en
otra zona horaria.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from ..broker.iol import tz_argentina
from ..config import DATA_DIR

DIR = DATA_DIR / "operador"
CANDADO_VENCE_SEG = 30 * 60   # un candado más viejo que esto es de una corrida que murió
# Estados del broker que garantizan que la orden NO entró. Cualquier otro (enviada, incierta, error,
# desconocido, o un intento sin respuesta) bloquea reenviar el mismo ticker/lado en el día.
ESTADOS_NO_ENVIADA = frozenset({"rechazada"})

log = logging.getLogger(__name__)


class OperadorOcupado(RuntimeError):
    """Ya hay otra corrida del operador en curso."""


def ahora_iso() -> str:
    return datetime.now(tz_argentina()).isoformat(timespec="seconds")


class Bitacora:
    def __init__(self, base: Path | None = None):
        self.dir = base or DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.archivo = self.dir / "bitacora.jsonl"
        self.estado_path = self.dir / "estado.json"
        self.candado_path = self.dir / "operador.lock"

    # --- eventos ------------------------------------------------------------
    def registrar(self, tipo: str, **datos) -> dict:
        ev = {"ts": ahora_iso(), "tipo": tipo, **datos}
        with open(self.archivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return ev

    def registrar_intento(self, ticker: str, lado: str, **datos) -> dict:
        """Llamar ANTES de `place_order`: si el proceso muere antes de registrar la respuesta, el intento
        igual bloquea el reenvío en el día (la orden pudo haber entrado)."""
        return self.registrar("intento_orden", ticker=ticker, lado=lado, **datos)

    def eventos(self, ultimos: int | None = None, tipo: str | None = None) -> list[dict]:
        if not self.archivo.exists():
            return []
        out = []
        for linea in self.archivo.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and (tipo is None or ev.get("tipo") == tipo):
                out.append(ev)
        return out[-ultimos:] if ultimos else out

    def ordenes_del_dia(self, dia: date) -> set[tuple[str, str]]:
        """(ticker, lado) enviados o intentados en `dia` (hora Argentina) que no fueron rechazados de forma
        definitiva: para no mandar dos veces la misma orden. Un error o timeout cuenta como enviada."""
        ultimo: dict[tuple[str, str], str] = {}
        for ev in self.eventos():
            if ev.get("tipo") not in ("orden", "intento_orden") or str(ev.get("ts", ""))[:10] != dia.isoformat():
                continue
            if not ev.get("ticker") or not ev.get("lado"):
                continue
            clave = (ev["ticker"], ev["lado"])
            ultimo[clave] = "intento" if ev["tipo"] == "intento_orden" else str(ev.get("estado"))
        return {k for k, estado in ultimo.items() if estado not in ESTADOS_NO_ENVIADA}

    # --- estado -------------------------------------------------------------
    def estado(self) -> dict:
        """Estado persistido. Si el archivo está roto, el operador queda PAUSADO (falla cerrado)."""
        if not self.estado_path.exists():
            return {"pausado": False, "ultimo_rebalanceo": None}
        try:
            datos = json.loads(self.estado_path.read_text(encoding="utf-8"))
            if not isinstance(datos, dict):
                raise ValueError("no es un objeto")
            return datos
        except (OSError, ValueError) as e:
            log.error("estado.json ilegible (%s): el operador queda pausado", e)
            return {"pausado": True, "motivo_pausa": f"estado.json ilegible: {e}", "ultimo_rebalanceo": None}

    def guardar_estado(self, **cambios) -> dict:
        nuevo = {**self.estado(), **cambios}
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(nuevo, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp, self.estado_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return nuevo

    def pausar(self, motivo: str = "manual") -> None:
        self.guardar_estado(pausado=True, motivo_pausa=motivo)
        self.registrar("pausa", motivo=motivo)

    def reanudar(self) -> None:
        self.guardar_estado(pausado=False, motivo_pausa=None)
        self.registrar("reanudar")

    # --- candado ------------------------------------------------------------
    @contextmanager
    def candado(self, vence_seg: float = CANDADO_VENCE_SEG) -> Iterator[None]:
        """Exclusión entre procesos: `with bit.candado(): ...`. Lanza OperadorOcupado si otra corrida lo tiene.
        Un candado más viejo que `vence_seg` se considera abandonado (proceso muerto) y se reemplaza."""
        self._tomar_candado(vence_seg)
        try:
            yield
        finally:
            self.candado_path.unlink(missing_ok=True)

    def _tomar_candado(self, vence_seg: float) -> None:
        for _ in range(2):
            try:
                fd = os.open(self.candado_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    edad = time.time() - self.candado_path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if edad <= vence_seg:
                    raise OperadorOcupado(f"otra corrida del operador está en curso ({self.candado_path})") from None
                self.candado_path.unlink(missing_ok=True)
                self.registrar("aviso", mensaje=f"candado abandonado de hace {edad:.0f}s: se reemplaza")
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(f"{os.getpid()} {ahora_iso()}")
            return
        raise OperadorOcupado("no pude tomar el candado del operador")
