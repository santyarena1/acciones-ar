import pytest

from src.operador.seguimiento import actualizar, resumen

BM0 = {"SPY": 100.0, "MERV": 1000.0}


def test_deposito_no_cuenta_como_ganancia():
    e, _ = actualizar(None, 500_000, 0, BM0)
    e, _ = actualizar(e, 700_000, 200_000, BM0)          # depositó 200 mil, sin ganar nada
    assert e["indice"] == pytest.approx(1.0)


def test_compara_contra_no_hacer_nada():
    e, _ = actualizar(None, 500_000, 0, BM0)
    e, _ = actualizar(e, 550_000, 0, {"SPY": 105.0, "MERV": 1050.0})   # operador +10%, benchmark +5%
    r = resumen(e)
    assert r["operador"] == pytest.approx(0.10) and r["no_hacer_nada"] == pytest.approx(0.05)
    assert r["diferencia"] == pytest.approx(0.05)


def test_aviso_de_caida_una_sola_vez_y_se_rearma_en_nuevo_maximo():
    e, _ = actualizar(None, 100, 0, BM0)
    e, aviso = actualizar(e, 80, 0, BM0)
    assert aviso and "20%" in aviso
    e, aviso = actualizar(e, 78, 0, BM0)
    assert aviso is None                                   # no repite
    e, _ = actualizar(e, 101, 0, BM0)                      # nuevo máximo: se rearma
    e, aviso = actualizar(e, 80, 0, BM0)
    assert aviso is not None


def test_sin_precios_de_benchmark_no_rompe():
    e, _ = actualizar(None, 100, 0, {})
    e, _ = actualizar(e, 110, 0, {})
    assert resumen(e)["no_hacer_nada"] == 0
