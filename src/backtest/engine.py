"""Backtest de rebalanceo mensual en USD CCL.

Estrategia: a fin de cada mes se calcula el score TÉCNICO de cada acción con datos hasta esa fecha
(indicadores causales => sin lookahead), se eligen las top_n con score >= score_minimo y se reparten en
partes iguales; el resto queda en caja (USD, rendimiento 0). Costos por lado sobre lo operado.

Benchmark: equiponderado de todo el universo disponible, rebalanceado mensualmente con los mismos costos.

Limitación: no usa fundamentales porque los actuales no son point-in-time (ver CLAUDE.md).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..analysis.technical import compute_indicators, technical_score

WARMUP = 200


def _panel(precios_usd: dict[str, pd.DataFrame]) -> pd.DataFrame:
    panel = pd.DataFrame({t: df["close"] for t, df in precios_usd.items()}).sort_index()
    return panel.ffill(limit=5)


def _fechas_rebalanceo(idx: pd.DatetimeIndex) -> set[pd.Timestamp]:
    s = pd.Series(idx, index=idx)
    return set(s.groupby([idx.year, idx.month]).max())


def _simular(panel: pd.DataFrame, elegir, costo: float) -> tuple[pd.Series, float]:
    ret = panel.pct_change(fill_method=None).fillna(0.0)
    rebal = _fechas_rebalanceo(panel.index)
    equity, valores, caja = 1.0, pd.Series(0.0, index=panel.columns), 1.0
    curva, turnover_total = [], 0.0
    for i, d in enumerate(panel.index):
        valores = valores * (1 + ret.loc[d])
        equity = float(valores.sum() + caja)
        if i >= WARMUP and d in rebal:
            pesos_old = valores / equity
            pesos_new = elegir(d)
            pesos_new = pesos_new.reindex(panel.columns).fillna(0.0)
            turnover = float((pesos_new - pesos_old).abs().sum())
            turnover_total += turnover
            equity -= turnover * costo * equity
            valores = pesos_new * equity
            caja = equity - float(valores.sum())
        curva.append(equity)
    return pd.Series(curva, index=panel.index).iloc[WARMUP:], turnover_total


def metricas(curva: pd.Series) -> dict:
    if len(curva) < 2:
        return {}
    r = curva.pct_change().dropna()
    anios = (curva.index[-1] - curva.index[0]).days / 365.25
    total = curva.iloc[-1] / curva.iloc[0] - 1
    cagr = (1 + total) ** (1 / anios) - 1 if anios > 0 else float("nan")
    vol = r.std() * math.sqrt(252)
    dd = (curva / curva.cummax() - 1).min()
    return {
        "retorno_total": round(total, 4),
        "cagr": round(cagr, 4),
        "volatilidad": round(vol, 4),
        "sharpe_rf0": round(cagr / vol, 2) if vol > 0 else float("nan"),
        "max_drawdown": round(float(dd), 4),
    }


def run_backtest(precios_usd: dict[str, pd.DataFrame], top_n: int = 6, score_minimo: float = 55,
                 costo_bps: float = 60) -> dict:
    panel = _panel(precios_usd)
    if len(panel) <= WARMUP + 21:
        raise ValueError(f"Historia insuficiente: {len(panel)} ruedas (mínimo {WARMUP + 21}).")
    costo = costo_bps / 1e4
    indicadores = {t: compute_indicators(panel[[t]].rename(columns={t: "close"}).dropna()) for t in panel.columns}

    def elegir_estrategia(d) -> pd.Series:
        scores = {}
        for t, ind in indicadores.items():
            if d in ind.index and pd.notna(ind.at[d, "sma200"]):
                s = technical_score(ind.loc[d])["score"]
                if pd.notna(s) and s >= score_minimo:
                    scores[t] = s
        top = sorted(scores, key=scores.get, reverse=True)[:top_n]
        return pd.Series({t: 1 / top_n for t in top}, dtype=float)

    def elegir_benchmark(d) -> pd.Series:
        disp = [t for t in panel.columns if pd.notna(panel.at[d, t])]
        return pd.Series({t: 1 / len(disp) for t in disp}, dtype=float) if disp else pd.Series(dtype=float)

    curva_e, turn_e = _simular(panel, elegir_estrategia, costo)
    curva_b, _ = _simular(panel, elegir_benchmark, costo)
    meses = max(1, len(curva_e) / 21)
    me, mb = metricas(curva_e), metricas(curva_b)
    me["turnover_anual"] = round(turn_e / meses * 12, 2)
    return {
        "estrategia": me,
        "benchmark": mb,
        "curvas": pd.DataFrame({"estrategia": curva_e, "benchmark": curva_b}),
        "desde": str(curva_e.index[0].date()),
        "hasta": str(curva_e.index[-1].date()),
    }
