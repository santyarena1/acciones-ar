"""Horario de BYMA: ruedas hábiles de 11:00 a 17:00 (hora Argentina, UTC-3 todo el año).

Todo se calcula en hora Argentina aunque la PC esté en otra zona (Windows con otra configuración regional,
VPS en UTC): `ahora_ar()` convierte desde el reloj del sistema con zoneinfo (o UTC-3 fijo si falta tzdata).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from ..broker.iol import tz_argentina

APERTURA, CIERRE = time(11, 0), time(17, 0)


def ahora_ar() -> datetime:
    """Hora Argentina *naive* (sin tzinfo), lista para comparar con APERTURA/CIERRE."""
    return datetime.now(tz_argentina()).replace(tzinfo=None)


def hoy_ar() -> date:
    return ahora_ar().date()


def feriados_ar(anios: list[int] | None = None) -> set[date]:
    """Feriados nacionales y puentes (argentinadatos, con caché anual). Si falla queda vacío para ese año:
    `mercado_abierto` lo detecta y no opera (mejor no operar que mandar órdenes en un feriado)."""
    from ..renta_fija.datos import feriados

    hoy = hoy_ar()
    return feriados(anios or [hoy.year, hoy.year + 1], {}, 20)


def es_habil(d: date, feriados: set[date]) -> bool:
    return d.weekday() < 5 and d not in feriados


def calendario_conocido(d: date, feriados: set[date]) -> bool:
    """Argentina tiene feriados todos los años: si no hay ninguno del año de `d`, el calendario no cargó."""
    return any(f.year == d.year for f in feriados)


def mercado_abierto(ahora: datetime, feriados: set[date], margen_min: int = 5,
                    exigir_calendario: bool = True) -> bool:
    """True si BYMA está operando a la hora `ahora` (naive en hora Argentina, o aware en cualquier zona).

    `margen_min`: no operar en los primeros/últimos minutos (subasta de apertura, spreads anchos, y que la
    orden llegue antes del cierre). Con `exigir_calendario`, sin feriados del año cargados no se opera."""
    if ahora.tzinfo is not None:
        ahora = ahora.astimezone(tz_argentina()).replace(tzinfo=None)
    if exigir_calendario and not calendario_conocido(ahora.date(), feriados):
        return False
    if not es_habil(ahora.date(), feriados):
        return False
    margen = timedelta(minutes=max(0, int(margen_min)))
    desde = datetime.combine(ahora.date(), APERTURA) + margen
    hasta = datetime.combine(ahora.date(), CIERRE) - margen
    return desde <= ahora < hasta
