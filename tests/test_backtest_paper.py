from src.backtest.engine import run_backtest
from src.broker.paper import PaperBroker
from tests.conftest import serie


def test_backtest_corre_y_prefiere_tendencia():
    precios = {f"UP{i}": serie(0.0015, n=600, seed=i) for i in range(3)}
    precios.update({f"DN{i}": serie(-0.0015, n=600, seed=10 + i) for i in range(3)})
    r = run_backtest(precios, top_n=3, score_minimo=50, costo_bps=60)
    assert r["estrategia"]["retorno_total"] > r["benchmark"]["retorno_total"]
    assert r["estrategia"]["max_drawdown"] <= 0


def test_paper_broker(tmp_path):
    b = PaperBroker(100_000, path=tmp_path / "s.json")
    assert b.place_order("GGAL", "COMPRAR", 10, 5000)["estado"].startswith("ejecutada")
    assert b.get_cash_ars() == 50_000
    assert b.place_order("GGAL", "VENDER", 20, 5000)["estado"] == "rechazada"
    b2 = PaperBroker(0, path=tmp_path / "s.json")  # persiste
    assert b2.get_positions()["GGAL"]["cantidad"] == 10
