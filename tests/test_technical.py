import numpy as np
import pandas as pd

from src.analysis.technical import compute_indicators, rsi, technical_score
from tests.conftest import serie


def test_rsi_extremos():
    sube = pd.Series(np.arange(1, 60, dtype=float))
    assert rsi(sube).iloc[-1] > 99
    baja = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert rsi(baja).iloc[-1] < 1


def test_score_tendencia_alcista_mayor_que_bajista():
    up = technical_score(compute_indicators(serie(0.002)).iloc[-1])["score"]
    down = technical_score(compute_indicators(serie(-0.002)).iloc[-1])["score"]
    assert 0 <= down < up <= 100


def test_indicadores_son_causales():
    df = serie(0.001, n=300)
    full = compute_indicators(df)
    parcial = compute_indicators(df.iloc[:250])
    pd.testing.assert_series_equal(full.iloc[249], parcial.iloc[-1], check_names=False)


def test_poca_historia_no_rompe():
    res = technical_score(compute_indicators(serie(0.001, n=60)).iloc[-1])
    assert "tendencia" in res["componentes"] and 0 <= res["score"] <= 100
