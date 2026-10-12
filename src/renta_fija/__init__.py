"""Renta fija argentina: soberanos en dólares, Lecap/Boncap, CER y ONs en USD.

API pública:
- `cargar_renta_fija(fecha=None, inflacion_mensual=None, devaluacion_mensual=None) -> DataFrame`
- `resumen_curvas(df) -> dict`

Órdenes en IOL: los bonos/letras cotizan por cada 100 VN. `cantidad` = valor nominal (entero, en VN) y `precio` =
precio por 100 VN en la moneda de la especie (`ticker_iol` en pesos, `ticker_iol_usd` = especie "D" en dólares MEP).
Monto = cantidad x precio / 100.
"""
from .analisis import resumen_curvas
from .servicio import cargar_renta_fija

__all__ = ["cargar_renta_fija", "resumen_curvas"]
