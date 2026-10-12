"""Orquestación: datos -> indicadores -> scores -> señales."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .analysis.fundamental import fundamental_score
from .analysis.scoring import combined_score, signal
from .analysis.technical import compute_indicators, technical_score
from .data.prices import load_ccl, load_history, to_usd


def load_prices(universe: list[dict], settings: dict, iol_client=None) -> tuple[dict[str, pd.DataFrame], dict[str, float]]:
    """Devuelve ({ticker: df en USD CCL}, {ticker: último precio ARS})."""
    anios = settings["datos"]["historia_anios"]
    desde = date.today() - timedelta(days=int(365 * anios) + 30)
    fuente = settings["datos"]["fuente_precios"]
    ccl = load_ccl(desde)
    usd, ultimo_ars = {}, {}
    for a in universe:
        t = a["ticker"]
        try:
            ars = load_history(t, desde, fuente=fuente, iol_client=iol_client)
        except Exception as e:
            print(f"  [aviso] sin precios para {t}: {e}")
            continue
        if ars.empty:
            print(f"  [aviso] sin precios para {t}")
            continue
        ultimo_ars[t] = float(ars["close"].iloc[-1])
        usd[t] = to_usd(ars, ccl)
    return usd, ultimo_ars


def analyze(precios_usd: dict[str, pd.DataFrame], fundamentales: dict[str, dict], universe: list[dict],
            settings: dict, horizonte: str, en_cartera: set[str] | None = None) -> pd.DataFrame:
    en_cartera = en_cartera or set()
    sectores = {a["ticker"]: a["sector"] for a in universe}
    filas = []
    for a in universe:
        t = a["ticker"]
        df = precios_usd.get(t)
        tec, ind = {"score": float("nan"), "componentes": {}}, None
        if df is not None and len(df) >= 30:
            ind = compute_indicators(df).iloc[-1]
            tec = technical_score(ind)
        fund = fundamental_score(fundamentales.get(t, {}), sectores.get(t))
        comb = combined_score(tec["score"], fund["score"], fund["cobertura"], horizonte, settings)
        rsi_v = float(ind["rsi14"]) if ind is not None and pd.notna(ind.get("rsi14")) else None
        filas.append({
            "ticker": t,
            "sector": sectores.get(t),
            "score": comb["score"],
            "senal": signal(comb["score"], t in en_cartera, rsi_v, settings),
            "score_tecnico": tec["score"],
            "score_fundamental": fund["score"],
            "cobertura_fund": fund["cobertura"],
            "precio_usd": round(float(ind["close"]), 3) if ind is not None else None,
            "rsi14": round(rsi_v, 1) if rsi_v is not None else None,
            "mom_6m": round(float(ind["mom_6m"]), 3) if ind is not None and pd.notna(ind.get("mom_6m")) else None,
            "sobre_sma200": bool(ind["close"] > ind["sma200"]) if ind is not None and pd.notna(ind.get("sma200")) else None,
            "en_cartera": t in en_cartera,
            "nota": comb["nota"],
        })
    return pd.DataFrame(filas).set_index("ticker").sort_values("score", ascending=False)
