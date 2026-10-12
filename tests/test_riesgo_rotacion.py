"""Riesgo global y rotación por sector/región (funciones puras, datos sintéticos)."""
import math

import numpy as np
import pandas as pd
import pytest

from src.analysis import riesgo_global as rg
from src.analysis import rotacion as ro

IDX = pd.bdate_range("2020-01-01", periods=700)


def _px(drift: float, n: int = 700, vol: float = 0.01, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(100 * np.exp(np.cumsum(drift + rng.normal(0, vol, n))), index=IDX[:n])


def _datos(crash: bool) -> dict:
    spy = _px(0.0006)
    if crash:  # cae 35% en las últimas 120 ruedas
        spy.iloc[-120:] = spy.iloc[-121] * np.linspace(1, 0.65, 120)
    vix = pd.Series(np.where(np.arange(700) >= 580, 40.0, 14.0) if crash else 14.0, index=IDX)
    hyg = spy * 0.5 if crash else _px(0.0003, seed=1)
    ief = _px(0.0001, seed=2, vol=0.002)
    tnx, irx = pd.Series(4.0, index=IDX), pd.Series(5.0 if crash else 2.0, index=IDX)
    return {"spy": spy, "vix": vix, "hyg": hyg, "ief": ief, "tnx": tnx, "irx": irx}


def test_bajo_media_y_sin_historia_es_nan():
    s = pd.Series(np.r_[np.full(10, 10.0), np.full(5, 5.0)], index=IDX[:15])
    b = rg.bajo_media(s, 10)
    assert b.iloc[:9].isna().all() and b.iloc[-1] == 1.0 and b.iloc[9] == 0.0


def test_media_mensual_no_mira_el_mes_en_curso():
    s = pd.Series(np.linspace(100, 200, 400), index=pd.bdate_range("2021-01-01", periods=400))
    s.iloc[-3:] = 1.0  # derrumbe en los últimos días del mes que todavía no cerró
    if s.index[-1] != s.index[-1] + pd.offsets.MonthEnd(0):
        assert rg.bajo_media_mensual(s, 10).iloc[-1] == 0.0


def test_escala_lineal_satura():
    e = rg.escala_lineal(pd.Series([10.0, 27.5, 50.0]), 20, 35)
    assert list(e) == [0.0, 0.5, 1.0]


def test_crash_da_riesgo_alto_y_calma_bajo():
    cfg = rg.cfg_riesgo({})
    _, r_crash, d_crash = rg.serie_defensiva(_datos(True), cfg)
    _, r_calma, d_calma = rg.serie_defensiva(_datos(False), cfg)
    assert r_crash.iloc[-1] > 0.8 and d_crash.iloc[-1] == pytest.approx(cfg["defensivo_max"])
    assert r_calma.iloc[-1] <= 0.25 and d_calma.iloc[-1] == 0.0


def test_riesgo_compuesto_ignora_faltantes_y_pondera():
    sen = pd.DataFrame({"a": [1.0, np.nan], "b": [0.0, 0.0]}, index=IDX[:2])
    r = rg.riesgo_compuesto(sen, {"a": 3, "b": 1})
    assert r.iloc[0] == pytest.approx(0.75) and r.iloc[1] == 0.0


def test_defensivo_bruto_lineal_y_topes():
    cfg = rg.cfg_riesgo({})
    assert rg.defensivo_bruto(0.1, cfg) == 0.0
    assert rg.defensivo_bruto(0.5, cfg) == pytest.approx(0.4)
    assert rg.defensivo_bruto(0.99, cfg) == pytest.approx(0.8)
    assert rg.defensivo_bruto(float("nan"), cfg) == 0.0


def test_histeresis_no_va_y_vuelve_por_poco_pero_vuelve_a_cero():
    v = pd.Series([0.0, 0.08, 0.12, 0.05, 0.31, 0.24, 0.21, 0.0], index=IDX[:8])
    h = rg.histeresis(v, 0.1, 0.05, 0.8)
    assert list(h) == [0.0, 0.0, 0.1, 0.1, 0.3, 0.3, 0.3, 0.0]


def test_riesgo_global_resumen_en_castellano():
    out = rg.riesgo_global(_datos(True), {})
    assert out["defensivo"] == pytest.approx(0.8) and out["riesgo"] > 0.8
    texto = " ".join(out["motivos"])
    assert "debajo de su tendencia de 200 ruedas" in texto and "VIX" in texto and "invertida" in texto


def test_riesgo_global_sin_datos():
    out = rg.riesgo_global({}, {})
    assert out["riesgo"] is None and out["defensivo"] == 0.0


GRUPOS = {"tec": {"nombre": "Tecnología", "proxy": "XLK", "sectores": ["tecnologia"], "tickers": ["QQQ"]},
          "ene": {"nombre": "Energía", "proxy": "XLE", "sectores": ["energia_ext"]},
          "bra": {"nombre": "Brasil", "proxy": "EWZ", "tickers": ["ITUB", "PBR"]},
          "sal": {"nombre": "Salud", "proxy": "XLV", "sectores": ["salud_ext"]},
          "fin": {"nombre": "Financiero", "proxy": "XLF", "sectores": ["financiero_ext"]}}


def _series_grupos() -> dict:
    return {"XLK": _px(0.0015, seed=3), "XLE": _px(-0.0008, seed=4), "EWZ": _px(0.0002, seed=5),
            "XLV": _px(0.0005, seed=6), "XLF": _px(0.0, seed=7)}


def test_momentum_ajustado_necesita_un_anio():
    assert ro.momentum_ajustado(_px(0.001, n=200), ro.DEFAULTS) is None
    assert ro.momentum_ajustado(_px(0.002, seed=1), ro.DEFAULTS) > ro.momentum_ajustado(_px(-0.001, seed=1),
                                                                                         ro.DEFAULTS)


def test_multiplicadores_acotados_y_medio_neutro():
    m = ro.multiplicadores({"a": 1.0, "b": 2.0, "c": 3.0}, 0.5, 1.75)
    assert m == {"a": 0.5, "b": 1.0, "c": 1.75}
    assert ro.multiplicadores({"a": 1.0}, 0.5, 1.75) == {"a": 1.0}


def test_grupo_de_prioriza_ticker_sobre_sector():
    assert ro.grupo_de("PBR", "energia_ext", GRUPOS) == "bra"
    assert ro.grupo_de("XOM", "energia_ext", GRUPOS) == "ene"
    assert ro.grupo_de("ZZZ", "otro", GRUPOS) is None


def test_rotacion_favorece_lideres_y_castiga_rezagados():
    cfg = {**ro.DEFAULTS, "grupos": GRUPOS}
    r = ro.rotacion(_series_grupos(), {"AAPL": "tecnologia", "XOM": "energia_ext", "ITUB": "financiero_ext"}, cfg)
    assert r["mult_por_ticker"]["AAPL"] == 1.75 and r["mult_por_ticker"]["XOM"] == 0.5
    assert "Tecnología" in r["favorecidos"] and "Energía" in r["castigados"]
    assert r["motivos"] and "más peso" in r["motivos"][0]


def test_rotacion_con_pocos_grupos_no_inclina():
    cfg = {**ro.DEFAULTS, "grupos": GRUPOS, "min_grupos": 10}
    ev = ro.evaluar_grupos(_series_grupos(), cfg)
    assert all(v["multiplicador"] == 1.0 for v in ev.values())
    assert not math.isnan(ev["tec"]["puntaje"])
