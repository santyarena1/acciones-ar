import pandas as pd
import pytest

from src.portfolio.risk import RiskError, limit_price, validate_orders
from src.portfolio.rules import build_targets, generate_orders


def test_targets_respetan_topes(settings):
    scores = pd.DataFrame({"score": {"A": 90, "B": 85, "C": 80, "D": 75, "E": 30, "F": 50}})
    sectores = {"A": "bancos", "B": "bancos", "C": "bancos", "D": "energia", "E": "energia", "F": "telecom"}
    t = build_targets(scores, {"E": 0.2, "F": 0.1}, sectores, settings)
    p = settings["portfolio"]
    assert t["E"] == 0                                   # score bajo: salir
    assert t["F"] == pytest.approx(0.10)                 # zona media: mantener
    assert all(w <= p["peso_max_accion"] + 1e-9 for w in t.values())
    assert sum(t[x] for x in "ABC") <= p["peso_max_sector"] + 1e-9
    assert sum(t.values()) <= 1 - p["caja_minima"] + 1e-9


def test_ordenes_vende_primero_y_respeta_minimo(settings):
    targets = {"A": 0.15, "E": 0.0, "Z": 0.0001}
    pos = {"E": {"cantidad": 100}}
    precios = {"A": 1000.0, "E": 2000.0, "Z": 500.0}
    o = generate_orders(targets, pos, 1_000_000, precios, settings)
    assert list(o["lado"]) == ["VENDER", "COMPRAR"]
    assert o.loc[0, "cantidad"] == 100 and "Z" not in set(o["ticker"])
    assert o.loc[1, "cantidad"] == 180  # 15% de 1.2M / 1000


def test_precio_limite():
    assert limit_price("COMPRAR", 1000, 0.005) == 1005.0
    assert limit_price("VENDER", 1000, 0.005) == 995.0


def test_riesgo_bloquea_orden_grande(settings):
    o = pd.DataFrame([{"ticker": "A", "lado": "COMPRAR", "cantidad": 10_000, "precio_ref": 1000.0}])
    with pytest.raises(RiskError):
        validate_orders(o, settings)


def test_riesgo_bloquea_demasiadas_ordenes(settings):
    n = settings["riesgo"]["ordenes_max_por_corrida"] + 1
    o = pd.DataFrame([{"ticker": f"T{i}", "lado": "COMPRAR", "cantidad": 1, "precio_ref": 10.0} for i in range(n)])
    with pytest.raises(RiskError):
        validate_orders(o, settings)
