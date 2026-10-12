import math

import numpy as np
import pandas as pd
import pytest

from src.analysis.macro import asignacion_clases, regimen_macro
from src.analysis.relative import fundamental_relativo, mezclar, percentil, tecnico_relativo


def test_percentil_extremos_y_direccion():
    s = pd.Series({"a": 1.0, "b": 2.0, "c": 3.0, "d": np.nan})
    p = percentil(s)
    assert p["a"] == 0 and p["c"] == 1 and math.isnan(p["d"])
    assert percentil(s, mayor_es_mejor=False)["a"] == 1


def test_tecnico_relativo_ordena_por_momentum():
    ult = pd.DataFrame({"mom_12m_1m": np.linspace(-0.3, 0.6, 10), "mom_6m": np.linspace(-0.2, 0.4, 10)},
                       index=[f"T{i}" for i in range(10)])
    r = tecnico_relativo(ult, min_activos=8)
    assert r["T9"] == 100 and r["T0"] == 0


def test_tecnico_relativo_pocos_activos_es_nan():
    ult = pd.DataFrame({"mom_6m": [0.1, 0.2]}, index=["A", "B"])
    assert tecnico_relativo(ult, min_activos=8).isna().all()


def test_fundamental_relativo_por_grupo_y_pe_negativo_al_fondo():
    tickers = [f"A{i}" for i in range(6)]
    met = pd.DataFrame({"pe": [5, 8, 12, 20, 30, -4], "roe": [0.3, 0.25, 0.2, 0.1, 0.05, -0.1]}, index=tickers)
    r = fundamental_relativo(met, pd.Series("accion", index=tickers), pd.Series("industria", index=tickers), 6)
    assert r["A0"] == r.max() and r["A5"] == r.min()


def test_mezclar_usa_absoluto_si_falta_relativo():
    m = mezclar(pd.Series({"a": 80.0, "b": 60.0}), pd.Series({"a": 40.0}), 0.5)
    assert m["a"] == 60 and m["b"] == 60


def _serie(valores, dias=400):
    idx = pd.date_range("2025-01-01", periods=dias, freq="D")
    return pd.Series(np.linspace(valores[0], valores[1], dias), index=idx)


def test_regimen_adverso_con_riesgo_pais_alto_y_brecha_alta(settings):
    m = regimen_macro(_serie((900, 1400)), _serie((1500, 2000)), _serie((1000, 1300)), _serie((60, 40)), settings)
    assert m["regimen"] == "adverso" and m["score"] < 35
    assert m["brecha"] == pytest.approx(2000 / 1300 - 1)


def test_regimen_favorable(settings):
    m = regimen_macro(_serie((800, 450)), _serie((1500, 1530)), _serie((1480, 1500)), _serie((40, 60)), settings)
    assert m["regimen"] == "favorable"


def test_regimen_sin_datos(settings):
    assert regimen_macro(None, None, None, None, settings)["regimen"] == "sin datos"


@pytest.mark.parametrize("regimen", ["favorable", "neutral", "adverso"])
def test_asignacion_suma_uno_y_no_negativa(settings, regimen):
    for perfil in settings["perfiles"]:
        a = asignacion_clases(perfil, regimen, settings)
        assert sum(a.values()) == pytest.approx(1.0, abs=1e-3)
        assert all(v >= 0 for v in a.values())


def test_adverso_baja_argentina_y_sube_cedears(settings):
    # el mecanismo sigue disponible si se configura un ajuste (por defecto está apagado por evidencia)
    s = {**settings, "macro": {**settings["macro"], "ajuste_adverso": -0.35, "ajuste_favorable": 0.15}}
    base = s["perfiles"]["moderado"]
    a = asignacion_clases("moderado", "adverso", s)
    assert a["acciones_ar"] < base["acciones_ar"] and a["cedears"] > base["cedears"] and a["caja"] > base["caja"]


def test_por_defecto_el_regimen_ar_no_mueve_la_asignacion(settings):
    for regimen in ("favorable", "adverso"):
        assert asignacion_clases("moderado", regimen, settings) == settings["perfiles"]["moderado"]
