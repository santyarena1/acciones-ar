"""Series del mercado global para la capa táctica (S&P 500, VIX, crédito, tasas y ETFs de sectores/regiones).

Usa la caché de `load_many` (diaria) y descarta la vela de hoy si la rueda no cerró: las señales se calculan solo
con cierres diarios, así no cambian de una corrida de 15 minutos a la siguiente.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import time as dtime

import pandas as pd

from ..analysis.riesgo_global import SIMBOLOS
from ..analysis.rotacion import cfg_rotacion, proxies
from .prices import load_many, ruedas_cerradas

HISTORIA_DIAS = 800   # SMA 200 + 10 meses + histéresis: alcanza con ~2 años


def series_tacticas(settings: dict, ahora: datetime, hora_cierre: dtime) -> dict[str, pd.Series]:
    """{símbolo: cierre diario} para señales de riesgo y proxies de rotación. Lo que falle queda afuera."""
    simbolos = sorted(set(SIMBOLOS.values()) | set(proxies(cfg_rotacion(settings).get("grupos") or {})))
    desde = date.today() - timedelta(days=HISTORIA_DIAS)
    out = {}
    for s, df in load_many(simbolos, desde).items():
        df = ruedas_cerradas(df, ahora, hora_cierre)
        if df is not None and not df.empty:
            out[s] = df["close"]
    return out
