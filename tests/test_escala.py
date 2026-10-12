import pytest

from src.portfolio.escala import asequible, cantidad_posiciones, escalar

MODERADO = {"acciones_ar": 0.30, "cedears": 0.30, "bonos_usd": 0.20, "pesos": 0.15, "caja": 0.05}


def test_cantidad_posiciones():
    assert cantidad_posiciones(150_000, 40_000, 8) == 3
    assert cantidad_posiciones(30_000, 40_000, 8) == 0
    assert cantidad_posiciones(10_000_000, 40_000, 8) == 8


def test_con_500_mil_concentra_y_permite_invertir_todo(settings):
    s, r = escalar(settings, 500_000, MODERADO)
    assert r["acciones_ar"] == 3 and r["cedears"] == 3 and r["bonos_usd"] == 2 and r["pesos"] == 1
    assert s["estrategia"]["n_acciones_ar"] == 3
    # cada clase puede usar todo su presupuesto con sus posiciones
    assert s["portfolio"]["peso_max_accion"] >= 0.30 / 3 - 1e-9
    assert s["renta_fija"]["peso_max_instrumento"] >= 0.15 - 1e-9
    assert settings["estrategia"]["n_acciones_ar"] == 8       # no modifica el original


def test_con_mucho_capital_usa_los_maximos_configurados(settings):
    s, r = escalar(settings, 50_000_000, MODERADO)
    assert r["acciones_ar"] == settings["estrategia"]["n_acciones_ar"]
    assert s["portfolio"]["peso_max_accion"] == pytest.approx(settings["portfolio"]["peso_max_accion"])


def test_asequible():
    assert asequible(20_970, 50_000)
    assert not asequible(81_200, 50_000)
    assert not asequible(None, 50_000)
