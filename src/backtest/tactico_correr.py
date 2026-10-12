"""Corre el backtest táctico con datos reales (yfinance + argentinadatos). I/O: baja y cachea datos.

Uso: .venv/Scripts/python main.py backtest-tactico [--desde 2008-01-01] [--perfil moderado_agresivo] [--freq ME]
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..analysis.rotacion import cfg_rotacion, proxies
from . import tactico as bt

VARIANTES = {
    "perfil fijo": {},
    "+ régimen AR (actual)": {"ar_regimen": True},
    "+ riesgo global": {"ar_regimen": True, "global": True},
    "+ rotación": {"ar_regimen": True, "rotacion": True},
    "+ ambos": {"ar_regimen": True, "global": True, "rotacion": True},
    "perfil fijo + riesgo global": {"global": True},
    "perfil fijo + 20% refugio fijo": {"defensivo_fijo": 0.2},
}
# Elecciones nacionales argentinas (PASO, generales y balotajes). Fuente: Cámara Nacional Electoral / DINE.
ELECCIONES_AR = ["2007-10-28", "2009-06-28", "2011-08-14", "2011-10-23", "2013-08-11", "2013-10-27", "2015-08-09",
                 "2015-10-25", "2015-11-22", "2017-08-13", "2017-10-22", "2019-08-11", "2019-10-27", "2021-09-12",
                 "2021-11-14", "2023-08-13", "2023-10-22", "2023-11-19", "2025-10-26"]


def cargar(settings: dict, desde_datos: date = date(2005, 1, 1)) -> dict:
    from ..data.prices import load_ccl, load_many, load_oficial, load_riesgo_pais

    grupos = cfg_rotacion(settings)["grupos"]
    simbolos = sorted(set(bt.ADRS_AR) | set(bt.SENALES.values()) | set(proxies(grupos)) | {"GLD"})
    px = {s: df["close"] for s, df in load_many(simbolos, desde_datos).items()}
    rp = load_riesgo_pais(date(1999, 1, 1))
    ccl, oficial = load_ccl(date(2013, 1, 1)), load_oficial(date(2011, 1, 1))
    return bt.preparar(px, rp, ccl, oficial, grupos)


def comparar(datos: dict, settings: dict, perfil: str, freq: str = "ME", desde: str = "2008-01-01",
             variantes: dict | None = None, costo_bps: float | None = None) -> dict:
    costo = costo_bps if costo_bps is not None else settings["backtest"]["costo_bps"]
    por_anio = 52 if freq == "W-FRI" else 12
    res = {n: bt.simular(datos, settings, perfil, v, freq, desde, costo) for n, v in (variantes or VARIANTES).items()}
    total = pd.DataFrame({n: {**bt.metricas(r["curva"], por_anio), "turnover": round(r["turnover_anual"], 2)}
                          for n, r in res.items()}).T
    tramos = {n: bt.por_tramos(r["curva"], por_anio) for n, r in res.items()}
    filas = [{"variante": n, "tramo": t, **m} for n, d in tramos.items() for t, m in d.items()]
    return {"total": total, "tramos": pd.DataFrame(filas), "resultados": res}


def imprimir(c: dict) -> None:
    print("\nPeríodo completo:\n" + c["total"].to_string())
    t = c["tramos"]
    for col in ("cagr", "max_dd", "sharpe"):
        print(f"\nPor tramo — {col}:\n" + t.pivot(index="variante", columns="tramo", values=col).to_string())
