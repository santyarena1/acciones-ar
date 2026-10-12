"""Indicadores técnicos y score técnico 0-100.

Funciones puras: reciben precios (idealmente en USD CCL) y no hacen I/O.
Todos los indicadores son causales (solo usan datos pasados), así sirven para el backtest.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

DIAS_3M, DIAS_6M, DIAS_12M, DIAS_1M = 63, 126, 252, 21


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    up = d.clip(lower=0)
    dn = -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + au / ad)
    return out


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(s, fast) - ema(s, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """df con columna 'close' (y opcional 'volume'), índice de fechas ordenado."""
    c = df["close"].astype(float)
    out = pd.DataFrame(index=df.index)
    out["close"] = c
    out["sma50"] = sma(c, 50)
    out["sma200"] = sma(c, 200)
    out["rsi14"] = rsi(c, 14)
    out = out.join(macd(c))
    out["mom_3m"] = c / c.shift(DIAS_3M) - 1
    out["mom_6m"] = c / c.shift(DIAS_6M) - 1
    # 12 meses salteando el último mes (evita reversión de corto plazo)
    out["mom_12m_1m"] = c.shift(DIAS_1M) / c.shift(DIAS_12M) - 1
    out["vol_anual"] = c.pct_change().rolling(DIAS_3M, min_periods=40).std() * math.sqrt(252)
    out["dist_max_52s"] = c / c.rolling(DIAS_12M, min_periods=60).max() - 1
    if "volume" in df.columns:
        v = df["volume"].astype(float)
        out["vol_ratio"] = v.rolling(20).mean() / v.rolling(100, min_periods=50).mean()
    return out


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _rsi_component(r: float) -> float:
    """Timing: zona sana 40-65 = 1. Sobrecompra castiga fuerte, sobreventa moderado."""
    if r >= 80:
        return 0.15
    if r >= 65:
        return 1.0 - (r - 65) / 15 * 0.85
    if r >= 40:
        return 1.0
    if r >= 25:
        return 0.55 + (r - 25) / 15 * 0.45
    return 0.55


def technical_score(row: pd.Series) -> dict:
    """Score técnico 0-100 a partir de una fila de compute_indicators.

    Componentes (pesos): tendencia 35%, momentum 35%, MACD 15%, RSI 15%.
    Si falta algún componente, se re-pondera con los disponibles.
    """
    comps: dict[str, tuple[float, float]] = {}

    close, s50, s200 = row.get("close"), row.get("sma50"), row.get("sma200")
    if pd.notna(s200) and pd.notna(s50):
        comps["tendencia"] = (0.5 * (close > s200) + 0.5 * (s50 > s200), 0.35)
    elif pd.notna(s50):
        comps["tendencia"] = (float(close > s50), 0.35)

    moms = [row.get(k) for k in ("mom_3m", "mom_6m", "mom_12m_1m")]
    moms = [m for m in moms if pd.notna(m)]
    if moms:
        m = float(np.mean(moms))
        # -30% -> 0 ; +30% -> 1 (en USD)
        comps["momentum"] = (_clip01((m + 0.30) / 0.60), 0.35)

    if pd.notna(row.get("macd_hist")):
        comps["macd"] = (float(row["macd_hist"] > 0), 0.15)

    if pd.notna(row.get("rsi14")):
        comps["rsi"] = (_rsi_component(float(row["rsi14"])), 0.15)

    if not comps:
        return {"score": np.nan, "componentes": {}}
    total_w = sum(w for _, w in comps.values())
    score = sum(v * w for v, w in comps.values()) / total_w * 100
    return {"score": round(score, 1), "componentes": {k: round(v, 2) for k, (v, _) in comps.items()}}
