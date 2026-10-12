"""Métricas fundamentales por ticker.

Fuentes, en orden de prioridad:
1. data/fundamentals_manual.csv  (lo que cargues a mano desde balances CNV / reportes; pisa todo)
2. yfinance sobre el ADR (solo tickers con ADR en universe.yaml)

Los ratios son adimensionales, así que no dependen de la moneda. Ojo: yfinance a veces mezcla
estados en ARS con precio en USD para ADRs argentinos; validar valores raros antes de confiar.
"""
from __future__ import annotations

import math

import pandas as pd

from ..config import DATA_DIR

METRICAS = ["pe", "ev_ebitda", "pb", "roe", "operating_margin", "net_debt_ebitda", "revenue_growth", "fcf_yield"]


def _num(x):
    try:
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


def from_yf_info(info: dict) -> dict:
    """Mapea el dict `Ticker.info` de yfinance a nuestras métricas."""
    m = {
        "pe": _num(info.get("trailingPE")),
        "ev_ebitda": _num(info.get("enterpriseToEbitda")),
        "pb": _num(info.get("priceToBook")),
        "roe": _num(info.get("returnOnEquity")),
        "operating_margin": _num(info.get("operatingMargins")),
        "revenue_growth": _num(info.get("revenueGrowth")),
    }
    fcf, mcap = _num(info.get("freeCashflow")), _num(info.get("marketCap"))
    m["fcf_yield"] = fcf / mcap if fcf is not None and mcap else None
    deuda, caja, ebitda = _num(info.get("totalDebt")), _num(info.get("totalCash")), _num(info.get("ebitda"))
    if deuda is not None and ebitda and ebitda > 0:
        m["net_debt_ebitda"] = (deuda - (caja or 0.0)) / ebitda
    else:
        m["net_debt_ebitda"] = None
    return m


def load_manual(path=None) -> dict[str, dict]:
    p = path or DATA_DIR / "fundamentals_manual.csv"
    try:
        df = pd.read_csv(p)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return {}
    out = {}
    for _, row in df.iterrows():
        out[str(row["ticker"]).upper()] = {k: _num(row.get(k)) for k in METRICAS}
    return out


def load_fundamentals(universe: list[dict], usar_yfinance: bool = True) -> dict[str, dict]:
    manual = load_manual()
    out: dict[str, dict] = {}
    for a in universe:
        t, adr = a["ticker"], a.get("adr")
        m: dict = {k: None for k in METRICAS}
        if usar_yfinance and adr:
            try:
                import yfinance as yf
                m.update({k: v for k, v in from_yf_info(yf.Ticker(adr).info).items() if v is not None})
            except Exception as e:  # red caída, ticker deslistado, etc.
                print(f"  [aviso] fundamentales de {adr} no disponibles: {e}")
        m.update({k: v for k, v in manual.get(t, {}).items() if v is not None})
        out[t] = m
    return out
