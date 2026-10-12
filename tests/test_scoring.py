import math

from src.analysis.scoring import combined_score, signal


def test_pesos_por_horizonte(settings):
    assert combined_score(80, 40, 1.0, "corto", settings)["score"] == 68.0
    assert combined_score(80, 40, 1.0, "largo", settings)["score"] == 48.0


def test_poca_cobertura_usa_solo_tecnico(settings):
    r = combined_score(70, 10, 0.1, "largo", settings)
    assert r["score"] == 70 and "solo técnico" in r["nota"]


def test_senales(settings):
    assert signal(80, False, 50, settings) == "COMPRAR"
    assert signal(80, True, 50, settings) == "AGREGAR"
    assert signal(80, False, 85, settings) == "ESPERAR (sobrecompra)"
    assert signal(50, True, 50, settings) == "MANTENER"
    assert signal(30, True, 50, settings) == "REDUCIR / VENDER"
    assert signal(30, False, 50, settings) == "EVITAR"
    assert signal(math.nan, False, None, settings) == "SIN DATOS"
