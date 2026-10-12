"""Broker simulado: ejecuta al precio límite y guarda el estado (caja, posiciones, historial).

- Dónde se guarda: con DATABASE_URL, tabla `paper` clave 'cartera' (un upsert: atómico); si no, un JSON local.
  Pasar `path` fuerza el archivo.

- Lleva el precio promedio de compra (ppc) ponderado por posición. Igual que en IOL, el ppc NO
  incluye comisiones; las comisiones se descuentan/cargan en la caja.
- Comisión por lado (incluye derechos de mercado) configurable en el constructor.
- Renta fija: `mult=0.01` (cotiza cada 100 VN, cantidad en VN). Monto = cantidad * precio * mult.
- Persistencia atómica (archivo temporal + os.replace, o una sola sentencia en la base) y compatible con el
  JSON viejo (posiciones sin ppc).
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path

from ..config import DATA_DIR
from .base import Broker
from .iol import tz_argentina

COMISION_DEFAULT = 0.006  # por lado, incluye derechos de mercado
_LADOS = ("COMPRAR", "VENDER")


class PaperBroker(Broker):
    nombre = "paper"

    def __init__(self, capital_inicial_ars: float, path: Path | None = None,
                 comision: float = COMISION_DEFAULT, almacen=None):
        if comision < 0 or comision >= 1:
            raise ValueError(f"Comisión inválida: {comision} (tiene que estar entre 0 y 1).")
        self.comision = float(comision)
        self.almacen = almacen or _almacen_por_defecto(path)
        cargado = self.almacen.leer()
        self.state = (_normalizar_estado(cargado, capital_inicial_ars) if cargado is not None
                      else _estado_nuevo(capital_inicial_ars))

    @property
    def path(self) -> Path | None:
        return getattr(self.almacen, "path", None)

    # --- persistencia ----------------------------------------------------
    def _save(self) -> None:
        self.almacen.escribir(self.state)

    def reiniciar(self, capital_ars: float) -> None:
        """Borra la cartera de práctica y arranca de cero con `capital_ars` de caja."""
        capital = float(capital_ars)
        if not math.isfinite(capital) or capital < 0:
            raise ValueError("El capital de práctica tiene que ser un número mayor o igual a cero.")
        self.state = _estado_nuevo(capital)
        self._save()

    # --- consultas -------------------------------------------------------
    def get_positions(self) -> dict[str, dict]:
        out = {}
        for t, p in self.state["posiciones"].items():
            cantidad = int(p.get("cantidad", 0))
            if cantidad <= 0:
                continue
            precio = float(p.get("precio", 0) or 0)
            ppc = p.get("ppc")
            mult = float(p.get("mult", 1.0) or 1.0)
            out[t] = {
                "cantidad": cantidad,
                "precio": precio,
                "ppc": float(ppc) if ppc is not None else None,
                "valorizado": cantidad * precio * mult,
                "tipo": p.get("tipo", "accion"),
            }
        return out

    def get_cash_ars(self) -> float:
        return float(self.state["caja"])

    def depositar(self, monto: float) -> float:
        """Simula que el dueño ingresa plata a la cuenta de práctica. Devuelve la caja nueva."""
        if not monto or not math.isfinite(float(monto)) or monto <= 0:
            raise ValueError("El depósito tiene que ser mayor a cero.")
        self.state["caja"] = float(self.state["caja"]) + float(monto)
        self._save()
        return float(self.state["caja"])

    def historial(self) -> list[dict]:
        return [dict(h) for h in self.state["historial"]]

    # --- órdenes ---------------------------------------------------------
    def place_order(self, ticker: str, lado: str, cantidad: int, precio_limite: float,
                    mult: float = 1.0, tipo: str | None = None) -> dict:
        """Ejecuta al precio límite. `mult`=0.01 para bonos/letras/ONs; `tipo` opcional para la posición."""
        error = _validar(lado, cantidad, precio_limite) or _validar_mult(mult)
        if error:
            return _rechazo(error)
        cantidad, precio, mult = int(cantidad), float(precio_limite), float(mult)
        monto = cantidad * precio * mult
        comision = monto * self.comision
        actual = self.state["posiciones"].get(ticker, {"cantidad": 0, "precio": precio, "ppc": None})
        tenencia = int(actual.get("cantidad", 0))

        if lado == "COMPRAR":
            if monto + comision > self.state["caja"] + 1e-9:
                return _rechazo(f"caja insuficiente (necesitás ${monto + comision:,.2f} con comisión, "
                                f"tenés ${self.state['caja']:,.2f})")
            ppc_previo = actual.get("ppc")
            ppc_previo = float(ppc_previo) if ppc_previo is not None else float(actual.get("precio", precio))
            nueva_cantidad = tenencia + cantidad
            ppc = (tenencia * ppc_previo + cantidad * precio) / nueva_cantidad  # en unidades de precio
            caja = self.state["caja"] - monto - comision
        else:
            if cantidad > tenencia:
                return _rechazo(f"cantidad mayor a la tenencia ({cantidad} > {tenencia})")
            nueva_cantidad = tenencia - cantidad
            ppc = actual.get("ppc") if nueva_cantidad > 0 else None
            caja = self.state["caja"] + monto - comision

        nueva_pos = {**actual, "cantidad": nueva_cantidad, "precio": precio, "ppc": ppc, "mult": mult,
                     "tipo": tipo or actual.get("tipo", "accion")}
        op_id = f"paper-{len(self.state['historial']) + 1}"
        registro = {
            "id": op_id, "fecha": datetime.now(tz_argentina()).isoformat(timespec="seconds"), "ticker": ticker,
            "lado": lado, "cantidad": cantidad, "precio": precio, "mult": mult,
            "monto": round(monto, 2), "comision": round(comision, 2),
        }
        self.state = {
            **self.state,
            "caja": caja,
            "posiciones": {**self.state["posiciones"], ticker: nueva_pos},
            "historial": [*self.state["historial"], registro],
        }
        self._save()
        return {"estado": "ejecutada (paper)", "id": op_id,
                "mensaje": f"{lado} {cantidad} {ticker} @ {precio:,.2f} (comisión ${comision:,.2f})"}


def _validar(lado: str, cantidad: int, precio: float) -> str | None:
    if lado not in _LADOS:
        return f"lado inválido: {lado}"
    try:
        if int(cantidad) <= 0 or int(cantidad) != cantidad:
            return "la cantidad tiene que ser un entero mayor a cero"
        if not float(precio) > 0:
            return "el precio tiene que ser mayor a cero"
    except (TypeError, ValueError):
        return "cantidad o precio inválidos"
    return None


def _validar_mult(mult: float) -> str | None:
    try:
        return None if float(mult) > 0 else "el multiplicador de precio tiene que ser mayor a cero"
    except (TypeError, ValueError):
        return "multiplicador de precio inválido"


def _rechazo(mensaje: str) -> dict:
    return {"estado": "rechazada", "id": None, "mensaje": mensaje}


def _normalizar_estado(raw: dict, capital_inicial_ars: float) -> dict:
    """Acepta el JSON viejo ({caja, posiciones:{t:{cantidad, precio}}, historial}) y completa claves."""
    if not isinstance(raw, dict):
        raise ValueError("El estado paper no es un objeto JSON.")
    posiciones = {
        t: {"cantidad": int(p.get("cantidad", 0)), "precio": float(p.get("precio", 0) or 0),
            "ppc": p.get("ppc"), "mult": float(p.get("mult", 1.0) or 1.0), "tipo": p.get("tipo", "accion")}
        for t, p in (raw.get("posiciones") or {}).items()
    }
    return {
        "caja": float(raw.get("caja", capital_inicial_ars)),
        "posiciones": posiciones,
        "historial": list(raw.get("historial") or []),
    }


def _estado_nuevo(capital: float) -> dict:
    return {"caja": float(capital), "posiciones": {}, "historial": []}


class AlmacenArchivo:
    """Estado paper en un JSON local (escritura atómica)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def leer(self) -> dict | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ValueError(f"No pude leer el estado paper en {self.path}: {e}. "
                             "Revisalo o borralo para arrancar de cero.") from e

    def escribir(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


class AlmacenDB:
    """Estado paper en la tabla `paper` (clave 'cartera'): {caja, posiciones, historial}."""
    CLAVE = "cartera"

    def __init__(self, engine=None):
        self.engine = engine

    def leer(self) -> dict | None:
        from .. import db
        return db.kv_get("paper", self.CLAVE, None, self.engine)

    def escribir(self, state: dict) -> None:
        from .. import db
        db.kv_set("paper", self.CLAVE, state, self.engine)


def _almacen_por_defecto(path: Path | None):
    from .. import db
    if path is None and db.hay_db():
        return AlmacenDB()
    return AlmacenArchivo(Path(path) if path else DATA_DIR / "paper_state.json")
