import math

from src.analysis.scoring import combined_score, signal


def test_pesos_por_horizonte(settings):
    assert combined_score(80, 40, 1.0, "corto", settings)["score"] == 68.0
    assert combined_score(80, 40, 1.0, "largo", settings)["score"] == 48.0


def test_poca_cobertura_usa_neutro_en_lugar_de_fundamental(settings):
    # largo: 20% técnico + 80% fundamental; sin fundamentales el 80% va con 50 (neutro)
    r = combined_score(70, 10, 0.1, "largo", settings)
    assert r["score"] == 54.0 and "neutro" in r["nota"]


def test_etf_solo_tecnico(settings):
    r = combined_score(70, None, 0.0, "largo", settings, aplica_fundamental=False)
    assert r["score"] == 70 and "ETF" in r["nota"]


def test_sin_fundamentales_no_supera_a_uno_con_fundamentales_buenos(settings):
    sin = combined_score(80, None, 0.0, "mediano", settings)["score"]
    con = combined_score(80, 75, 1.0, "mediano", settings)["score"]
    assert con > sin


def test_senales(settings):
    assert signal(80, False, 50, settings, True, True) == "COMPRAR"
    assert signal(80, False, 50, settings).startswith("ESPERAR")  # sin SMA200 conocida no abre posición
    assert signal(80, True, 50, settings) == "AGREGAR"
    assert signal(80, False, 85, settings, True, True) == "ESPERAR (sobrecompra)"
    assert signal(50, True, 50, settings) == "MANTENER"
    assert signal(30, True, 50, settings) == "REDUCIR / VENDER"
    assert signal(30, False, 50, settings) == "EVITAR"
    assert signal(math.nan, False, None, settings) == "SIN DATOS"
