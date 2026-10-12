"""Punto de entrada: arma la tabla de renta fija del día (I/O + valuación + análisis)."""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from . import datos
from .analisis import analizar
from .calculos import fecha_liquidacion, sumar_dias_habiles
from .valuacion import Contexto, evaluar, mep_implicito, terminos_dinamicos

log = logging.getLogger(__name__)


def cer_referencia(serie: dict[date, float], liquidacion: date, rezago: int, feriados: set[date]) -> float | None:
    """CER de `rezago` días hábiles antes de la liquidación (o el último publicado anterior a esa fecha)."""
    if not serie:
        return None
    objetivo = sumar_dias_habiles(liquidacion, -rezago, feriados)
    previas = [d for d in serie if d <= objetivo]
    return serie[max(previas)] if previas else None


def _contexto(fecha: date, p: dict[str, Any], fer: set[date], cotiz: pd.DataFrame, cer: dict[date, float],
              inflacion: float | None, devaluacion: float | None) -> Contexto:
    liq = fecha_liquidacion(fecha, fer, int(p.get("plazo_liquidacion", 1)))
    return Contexto(
        liquidacion=liq,
        cer_ref=cer_referencia(cer, liq, int(p.get("rezago_cer_habiles", 10)), fer),
        mep=mep_implicito(cotiz),
        inflacion_mensual=float(inflacion if inflacion is not None else p.get("inflacion_esperada_mensual", 0.02)),
        devaluacion_mensual=float(devaluacion if devaluacion is not None
                                  else p.get("devaluacion_esperada_mensual", 0.01)),
    )


def tabla_valuada(instrumentos: dict[str, dict[str, Any]], cotiz: pd.DataFrame, ctx: Contexto) -> pd.DataFrame:
    """Valúa cada instrumento (puro). Los vencidos se descartan; un error en uno no frena al resto."""
    filas = []
    for ticker, terminos in instrumentos.items():
        try:
            fila = evaluar(ticker, terminos, cotiz, ctx)
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as e:
            log.warning("Renta fija: no pude valuar %s (%s)", ticker, e)
            continue
        if fila is not None:
            filas.append(fila)
    return pd.DataFrame(filas)


def cargar_renta_fija(fecha: date | None = None, inflacion_mensual: float | None = None,
                      devaluacion_mensual: float | None = None, refrescar: bool = False,
                      ruta_config: Path | None = None) -> pd.DataFrame:
    """Tabla de renta fija (una fila por instrumento con precio) lista para asignar entre clases de activo.

    Columnas principales: ticker, clase (soberano_usd|lecap|boncap|cer|on_usd), familia, precio (moneda del
    instrumento, por 100 VN), precio_ars, ticker_iol / ticker_iol_usd, tir (efectiva anual: USD, nominal ARS o real
    CER según `tipo_tasa`), tem, duration (modificada, años), vencimiento, paridad, volumen_ars, carry_real,
    carry_usd, spread_vs_curva_pb, senal_rv, spread_ley_pb, breakeven_mensual, score_rf (0-100, VACÍO si el
    instrumento no pasa el filtro de calidad: no comprar), score_rf_bruto, apto_compra, motivo_no_apto.
    Los parámetros salen de config/renta_fija.yaml; inflación/devaluación mensual esperadas se pueden pisar acá.
    """
    fecha = fecha or date.today()
    cfg = datos.cargar_config(ruta_config)
    p = cfg["parametros"]
    fuentes, timeout = p.get("fuentes", {}), float(p.get("timeout_s", 20))
    fer = datos.feriados([fecha.year, fecha.year + 1], fuentes, timeout)
    ttl = p.get("cache_ttl_min")
    cotiz = datos.cotizaciones(fecha, fuentes, timeout, refrescar, float(ttl) if ttl is not None else None)
    cer = datos.serie_cer(fecha, fuentes, timeout, refrescar)
    instrumentos = {**cfg["instrumentos"],
                    **terminos_dinamicos(datos.letras(fecha, fuentes, timeout, refrescar), cfg["instrumentos"])}
    ctx = _contexto(fecha, p, fer, cotiz, cer, inflacion_mensual, devaluacion_mensual)
    df = tabla_valuada(instrumentos, cotiz, ctx)
    if df.empty:
        return df
    out = analizar(df[df["precio"].notna()].reset_index(drop=True), p)
    return out.assign(fecha=fecha, liquidacion=ctx.liquidacion, mep=ctx.mep, cer_ref=ctx.cer_ref)
