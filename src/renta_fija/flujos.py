"""Generación de flujos de fondos a partir de los términos de config/renta_fija.yaml (puro, sin I/O).

Formatos soportados por instrumento (todo por 100 VN originales):
- `pago_final` + `vencimiento`: cupón cero (Lecap, Boncap, Boncer cupón cero).
- `flujos: [[fecha, interes, amortizacion], ...]`: cronograma explícito (Bonares nuevos, ONs, Bopreal).
- Paramétrico (canje 2020, Boncer con cupón, Bontes): `fechas` + `cupones` (step-up) + `amortizacion`.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Any

from .calculos import Flujo

MESES_ANIO = 12


def _a_fecha(x: Any) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def sumar_meses(d: date, meses: int) -> date:
    """Suma meses manteniendo el día (si el mes es más corto, último día del mes)."""
    total = d.month - 1 + meses
    anio, mes = d.year + total // MESES_ANIO, total % MESES_ANIO + 1
    dia = min(d.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def fechas_periodicas(primera: date, vencimiento: date, meses: int) -> list[date]:
    """Fechas de pago desde `primera` hasta `vencimiento` inclusive, cada `meses` meses (anclado al día de `primera`)."""
    out, k = [], 0
    while True:
        d = sumar_meses(primera, meses * k)
        if d > vencimiento:
            break
        out.append(d)
        k += 1
    if out and out[-1] != vencimiento:
        out.append(vencimiento)
    return out


def tasa_vigente(cupones: list[tuple[date, float]], inicio_periodo: date) -> float:
    """Tasa anual (%) vigente al inicio del período de devengamiento (step-up por tramos)."""
    vigente = 0.0
    for desde, tasa in sorted(cupones):
        if desde <= inicio_periodo:
            vigente = tasa
    return vigente


def cuotas_amortizacion(spec: dict[str, Any], fechas_pago: list[date]) -> dict[date, float]:
    """Cuotas de capital (% del VN original) por fecha. Cuotas iguales con primera opcional distinta."""
    inicio = _a_fecha(spec["inicio"])
    n = int(spec["cuotas"])
    fechas = [d for d in fechas_pago if d >= inicio][:n]
    if len(fechas) != n:
        raise ValueError(f"cronograma de amortización inconsistente: {len(fechas)} fechas para {n} cuotas")
    primera = spec.get("primera_pct")
    if primera is None:
        return {d: 100.0 / n for d in fechas}
    resto = (100.0 - float(primera)) / (n - 1) if n > 1 else 0.0
    return {d: (float(primera) if i == 0 else resto) for i, d in enumerate(fechas)}


def _flujos_parametricos(t: dict[str, Any]) -> list[Flujo]:
    f = t["fechas"]
    meses = int(f.get("meses", 6))
    venc = _a_fecha(t["vencimiento"])
    pagos = fechas_periodicas(_a_fecha(f["primera"]), venc, meses)
    cupones = [(_a_fecha(d), float(r)) for d, r in t["cupones"]]
    amort = cuotas_amortizacion(t["amortizacion"], pagos)
    residual, anterior, out = 100.0, _a_fecha(t["emision"]), []
    for d in pagos:
        interes = residual * tasa_vigente(cupones, anterior) / 100.0 * meses / MESES_ANIO
        capital = amort.get(d, 0.0)
        out.append(Flujo(d, interes, capital))
        residual -= capital
        anterior = d
    return out


def generar_flujos(terminos: dict[str, Any]) -> list[Flujo]:
    """Flujos por 100 VN originales según el formato de términos del instrumento."""
    if "flujos" in terminos:
        return sorted((Flujo(_a_fecha(d), float(i), float(a)) for d, i, a in terminos["flujos"]),
                      key=lambda x: x.fecha)
    if "pago_final" in terminos:
        pago = float(terminos["pago_final"])
        return [Flujo(_a_fecha(terminos["vencimiento"]), pago - 100.0, 100.0)]
    if "fechas" in terminos:
        return _flujos_parametricos(terminos)
    raise ValueError(f"términos sin formato reconocido: {sorted(terminos)}")


def inicio_devengamiento(terminos: dict[str, Any]) -> date:
    """Fecha desde la que devenga el primer cupón (para cupón corrido antes del primer pago)."""
    return _a_fecha(terminos.get("emision") or terminos["vencimiento"])


def validar_amortizacion(flujos: list[Flujo], tolerancia: float = 0.01) -> bool:
    """El capital total amortizado tiene que sumar 100 (salvo cronogramas truncados a futuro)."""
    return abs(sum(f.amortizacion for f in flujos) - 100.0) <= tolerancia
