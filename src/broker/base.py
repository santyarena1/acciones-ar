"""Interfaz común de broker. El análisis nunca depende de un broker concreto."""
from __future__ import annotations

from abc import ABC, abstractmethod


class Broker(ABC):
    """Contrato mínimo que tiene que cumplir cualquier broker (IOL, paper, Bull Market a futuro).

    Forma de una posición (igual en todos los brokers):
        {"cantidad": int, "precio": float, "ppc": float | None, "valorizado": float | None,
         "tipo": "accion" | "cedear" | "bono" | "letra" | "on"}
    En renta fija `cantidad` es VN y `precio`/`ppc` son cada 100 VN; `valorizado` está en moneda.
    Resultado de place_order / cancel_order:
        {"estado": str, "id": str | int | None, "mensaje": str}
    """

    nombre: str = "base"

    @abstractmethod
    def get_positions(self) -> dict[str, dict]:
        """{ticker: {"cantidad", "precio", "ppc", "valorizado", "tipo"}} (sin FCI/cauciones/opciones)."""

    @abstractmethod
    def get_cash_ars(self) -> float:
        """Pesos disponibles para operar."""

    @abstractmethod
    def place_order(self, ticker: str, lado: str, cantidad: int, precio_limite: float,
                    mult: float = 1.0) -> dict:
        """Envía una orden límite. Devuelve {"estado", "id", "mensaje"}.

        `mult` pasa el precio de pantalla a pesos por unidad: 1.0 para acciones/CEDEARs, 0.01 para
        bonos/letras/ONs (cotizan cada 100 VN; la cantidad va en VN). Monto = cantidad * precio * mult.
        """

    # --- opcionales: los brokers que no los soportan heredan estos defaults ---
    def get_quote(self, ticker: str) -> dict | None:
        """Cotización actual (último, puntas, volumen). None si el broker no da cotizaciones."""
        return None

    def open_orders(self) -> list[dict]:
        """Órdenes pendientes. Lista vacía si el broker no maneja órdenes abiertas."""
        return []

    def cancel_order(self, order_id: str | int) -> dict:
        """Cancela una orden pendiente. Por defecto: no soportado."""
        return {"estado": "no_soportado", "id": order_id,
                "mensaje": f"El broker '{self.nombre}' no permite cancelar órdenes."}
