"""Broker simulado: ejecuta al precio límite y guarda el estado en un JSON."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..config import DATA_DIR
from .base import Broker


class PaperBroker(Broker):
    nombre = "paper"

    def __init__(self, capital_inicial_ars: float, path: Path | None = None):
        self.path = path or DATA_DIR / "paper_state.json"
        if self.path.exists():
            self.state = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.state = {"caja": float(capital_inicial_ars), "posiciones": {}, "historial": []}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_positions(self) -> dict[str, dict]:
        return {t: dict(p) for t, p in self.state["posiciones"].items() if p["cantidad"] > 0}

    def get_cash_ars(self) -> float:
        return float(self.state["caja"])

    def place_order(self, ticker: str, lado: str, cantidad: int, precio_limite: float) -> dict:
        monto = cantidad * precio_limite
        pos = self.state["posiciones"].setdefault(ticker, {"cantidad": 0, "precio": precio_limite})
        if lado == "COMPRAR":
            if monto > self.state["caja"]:
                return {"estado": "rechazada", "mensaje": "caja insuficiente"}
            self.state["caja"] -= monto
            pos["cantidad"] += cantidad
        else:
            if cantidad > pos["cantidad"]:
                return {"estado": "rechazada", "mensaje": "cantidad mayor a la tenencia"}
            self.state["caja"] += monto
            pos["cantidad"] -= cantidad
        pos["precio"] = precio_limite
        self.state["historial"].append({
            "fecha": datetime.now().isoformat(timespec="seconds"), "ticker": ticker, "lado": lado,
            "cantidad": cantidad, "precio": precio_limite,
        })
        self._save()
        return {"estado": "ejecutada (paper)"}
