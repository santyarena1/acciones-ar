"""Calendario de eventos de alto impacto (config/eventos.yaml). Funciones puras, sin I/O.

Cada evento tiene fecha, ventana previa (`dias_antes`) y posterior (`dias_despues`, por defecto 0) y cuánto se
reduce la exposición argentina mientras la ventana está abierta (`reduccion_ar`, 0..1; 0 = solo informativo).
Solo se cargan fechas con fuente; lo dudoso queda afuera.
"""
from __future__ import annotations

from datetime import date, timedelta


def _fecha(x) -> date | None:
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x))
    except ValueError:
        return None


def eventos_activos(eventos: list[dict], hoy: date) -> list[dict]:
    """Eventos cuya ventana [fecha - dias_antes, fecha + dias_despues] contiene `hoy` (días corridos)."""
    out = []
    for e in eventos or []:
        f = _fecha(e.get("fecha"))
        if f is None:
            continue
        ini = f - timedelta(days=int(e.get("dias_antes", 0)))
        fin = f + timedelta(days=int(e.get("dias_despues", 0)))
        if ini <= hoy <= fin:
            out.append({**e, "fecha": f.isoformat(), "dias_para_evento": (f - hoy).days})
    return sorted(out, key=lambda e: e["fecha"])


def proximos(eventos: list[dict], hoy: date, dias: int = 60) -> list[dict]:
    """Eventos de los próximos `dias` (para mostrar, aunque todavía no estén en ventana)."""
    out = []
    for e in eventos or []:
        f = _fecha(e.get("fecha"))
        if f is not None and hoy <= f <= hoy + timedelta(days=dias):
            out.append({**e, "fecha": f.isoformat(), "dias_para_evento": (f - hoy).days})
    return sorted(out, key=lambda e: e["fecha"])


def reduccion_ar(activos: list[dict]) -> float:
    """La mayor reducción entre los eventos en ventana (no se suman: es la misma cobertura)."""
    vals = [float(e.get("reduccion_ar") or 0.0) for e in activos]
    return max([0.0, *vals])


def texto_evento(e: dict) -> str:
    d = e.get("dias_para_evento")
    cuando = "hoy" if d == 0 else f"en {d} días" if d and d > 0 else f"hace {-d} días"
    return f"{e.get('nombre', 'evento')} ({e['fecha']}, {cuando})"
