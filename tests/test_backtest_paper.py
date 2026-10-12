from src.backtest.engine import run_backtest
from tests.conftest import serie


def test_backtest_corre_y_prefiere_tendencia():
    precios = {f"UP{i}": serie(0.0015, n=600, seed=i) for i in range(3)}
    precios.update({f"DN{i}": serie(-0.0015, n=600, seed=10 + i) for i in range(3)})
    r = run_backtest(precios, top_n=3, score_minimo=50, costo_bps=60)
    assert r["estrategia"]["retorno_total"] > r["benchmark"]["retorno_total"]
    assert r["estrategia"]["max_drawdown"] <= 0
