"""Interfaz común de broker. El análisis nunca depende de un broker concreto."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Broker(ABC):
    nombre: str = "base"

    @abstractmethod
    def get_positions(self) -> dict[str, dict]:
        """{ticker: {"cantidad": int, "precio": float}}"""

    @abstractmethod
    def get_cash_ars(self) -> float:
        """Pesos disponibles para operar."""

    @abstractmethod
    def place_order(self, ticker: str, lado: str, cantidad: int, precio_limite: float) -> dict:
        """Envía una orden límite. Devuelve un dict con el resultado (id, estado, mensaje)."""
