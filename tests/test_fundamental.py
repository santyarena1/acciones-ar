import math

from src.analysis.fundamental import fundamental_score


BUENA = {"pe": 6, "ev_ebitda": 4, "pb": 0.6, "fcf_yield": 0.12, "roe": 0.25, "operating_margin": 0.3,
         "net_debt_ebitda": -0.5, "revenue_growth": 0.25}
MALA = {"pe": -5, "ev_ebitda": 20, "pb": 4, "fcf_yield": -0.05, "roe": -0.1, "operating_margin": -0.05,
        "net_debt_ebitda": 5, "revenue_growth": -0.2}


def test_extremos():
    assert fundamental_score(BUENA)["score"] == 100
    assert fundamental_score(MALA)["score"] == 0
    assert fundamental_score(BUENA)["cobertura"] == 1.0


def test_sin_datos():
    r = fundamental_score({})
    assert math.isnan(r["score"]) and r["cobertura"] == 0


def test_bancos_ignoran_deuda_ebitda():
    r = fundamental_score({**BUENA, "net_debt_ebitda": 10, "ev_ebitda": 50}, sector="bancos")
    assert r["score"] == 100 and "salud" not in r["bloques"]
