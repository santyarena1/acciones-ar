"""Broker simulado: ejecuta al precio límite y guarda el estado en un JSON.

- Lleva el precio promedio de compra (ppc) ponderado por posición. Igual que en IOL, el ppc NO
  incluye comisiones; las comisiones se descuentan/cargan en la caja.
- Comisión por lado (incluye derechos de mercado) configurable en el constructor.
- Renta fija: `mult=0.01` (cotiza cada 100 VN, cantidad en VN). Monto = cantidad * precio * mult.
- Persistencia atómica (archivo temporal + os.replace) y compatible con el JSON viejo
  (posiciones sin ppc).
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

from ..config import DATA_DIR
from .base import Broker

COMISION_DEFAULT = 0.006  # por lado, incluye derechos de mercado
_LADOS = ("COMPRAR", "VENDER")


class PaperBroker(Broker):
    nombre = "paper"

    def __init__(self, capital_inicial_ars: float, path: Path | None = None,
                 comision: float = COMISION_DEFAULT):
        if comision < 0 or comision >= 1:
            raise ValueError(f"Comisión inválida: {comision} (tiene que estar entre 0 y 1).")
        self.comision = float(comision)
        self.path = Path(path) if path else DATA_DIR / "paper_state.json"
        if self.path.exists():
            try:
                cargado = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise ValueError(f"No pude leer el estado paper en {self.path}: {e}. "
                                 "Revisalo o borralo para arrancar de cero.") from e
            self.state = _normalizar_estado(cargado, capital_inicial_ars)
        else:
            self.state = {"caja": float(capital_inicial_ars), "posiciones": {}, "historial": []}

    # --- persistencia ----------------------------------------------------
    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.state, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

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
        if not monto or monto <= 0:
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
            "id": op_id, "fecha": datetime.now().isoformat(timespec="seconds"), "ticker": ticker,
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
