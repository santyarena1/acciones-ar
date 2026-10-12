"""El backtest no puede operar al mismo cierre que usa para decidir (lookahead de ejecución)."""
import numpy as np
import pandas as pd

from src.backtest import engine


def test_la_orden_se_ejecuta_la_rueda_siguiente_a_la_senal():
    idx = pd.bdate_range("2024-01-01", periods=engine.WARMUP + 60)
    panel = pd.DataFrame({"A": np.full(len(idx), 100.0)}, index=idx)
    rebal = sorted(d for d in engine._fechas_rebalanceo(idx) if idx.get_loc(d) >= engine.WARMUP)
    d = rebal[0]
    i = idx.get_loc(d)
    panel.iloc[i + 1:, 0] = 110.0   # salta 10% la rueda siguiente a la señal
    curva, _, _ = engine._simular(panel, lambda f, p: pd.Series({"A": 1.0}), 0.0)
    # quien decide con el cierre de d recién compra al cierre de d+1: no captura ese salto
    assert curva.iloc[-1] == 1.0


def test_zona_de_mantener_no_rota_lo_que_sigue_bien():
    scores = pd.Series({"A": 50.0, "B": 90.0, "C": 85.0})
    sobre = pd.Series({"A": True, "B": True, "C": False})
    pesos = pd.Series({"A": 0.6, "B": 0.0, "C": 0.0})
    w = engine._elegir_con_zona(scores, sobre, pesos, 2, 70, 40, True)
    assert w["A"] == 0.6 and w["B"] == 0.4 and "C" not in w   # A se queda; C no entra (bajo SMA200)
    w2 = engine._elegir_con_zona(scores, sobre, pesos, 2, 70, None, False)
    assert "A" not in w2                                        # modo viejo: rota todo
