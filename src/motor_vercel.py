"""Punto de entrada del motor cuando corre como función de Vercel (cron cada hora + botón "Revisar ahora").

Hace lo mismo que el workflow: esquema (idempotente) -> claves cifradas desde la base -> reporte semanal
(lunes y martes) -> un ciclo del operador. Devuelve solo un estado genérico; el detalle queda en `eventos`.
"""
from __future__ import annotations


def ejecutar(solo_analisis: bool = False, forzar: bool = False) -> dict:
    from . import db
    from .config import load_settings, load_universe
    from .operador.ejecutor import operar
    from .operador.mercado import ahora_ar
    from .secretos import cargar_secretos_en_entorno

    db.aplicar_esquema()
    cargar_secretos_en_entorno()
    if ahora_ar().weekday() <= 1:                       # el reporte sale lunes a última hora o martes
        _reportes()
    r = operar(load_settings(), load_universe(), forzar_horario=forzar, solo_analisis=solo_analisis)
    return {"ok": r.estado != "error", "estado": r.estado, "ordenes": len(r.enviadas)}


def _reportes() -> None:
    from .data import gorostiaga
    try:
        gorostiaga.actualizar()
    except Exception as e:  # noqa: BLE001 - el reporte nunca frena la corrida
        from .operador.bitacora import abrir_bitacora
        abrir_bitacora().registrar("error", error=f"reporte semanal: {type(e).__name__}", origen="vercel")
