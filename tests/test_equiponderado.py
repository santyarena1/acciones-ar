"""Acciones AR equiponderadas: las N más líquidas del panel líder, con salida por margen de liquidez."""
import numpy as np
import pandas as pd
import pytest

from src.backtest import engine
from src.portfolio.equiponderado import objetivos_equiponderados


def _cfg(settings, n=3, margen=1):
    return {**settings, "estrategia": {"acciones_ar": "equiponderado", "n_acciones_ar": n,
                                       "margen_salida_liquidez": margen, "salir_por_stop": True}}


def _ranking(vols: dict, **extra) -> pd.DataFrame:
    df = pd.DataFrame({"vol_ars_20d": vols})
    df["tipo"], df["panel"], df["liquido"], df["calidad_datos"], df["alertas"] = "accion", "lider", True, "", ""
    for col, vals in extra.items():
        for t, v in vals.items():
            df.at[t, col] = v
    return df


VOLS = {"A": 900.0, "B": 800.0, "C": 700.0, "D": 600.0, "E": 500.0, "F": 400.0}


def test_elige_las_n_mas_liquidas_en_partes_iguales(settings):
    t = objetivos_equiponderados(_ranking(VOLS), {}, 0.30, _cfg(settings))
    assert {k for k, w in t.items() if w > 0} == {"A", "B", "C"}
    assert t["A"] == pytest.approx(0.10)


def test_tope_por_accion(settings):
    t = objetivos_equiponderados(_ranking(VOLS), {}, 0.60, _cfg(settings))
    assert t["A"] == pytest.approx(settings["portfolio"]["peso_max_accion"])


def test_tenida_dentro_del_margen_se_queda_y_fuera_se_vende(settings):
    s = _cfg(settings, n=3, margen=1)
    t = objetivos_equiponderados(_ranking(VOLS), {"D": 0.05, "E": 0.05}, 0.30, s)
    assert t["D"] > 0          # puesto 4 <= N + margen
    assert t["E"] == 0         # puesto 5 > N + margen
    assert sum(1 for w in t.values() if w > 0) == 3


def test_datos_rotos_no_se_toca_y_ocupa_presupuesto(settings):
    r = _ranking(VOLS, calidad_datos={"A": "precio viejo"})
    t = objetivos_equiponderados(r, {"A": 0.10}, 0.30, _cfg(settings))
    assert "A" not in t
    assert sum(t.values()) == pytest.approx(0.20, abs=1e-3)


def test_stop_y_panel_general_salen(settings):
    r = _ranking(VOLS, alertas={"B": "REVISAR STOP: -30% desde el máximo"}, panel={"Z": "general"},
                 vol_ars_20d={"Z": 5000.0})
    r.loc["Z", ["tipo", "liquido", "calidad_datos", "alertas"]] = ["accion", True, "", ""]
    t = objetivos_equiponderados(r, {"B": 0.1, "Z": 0.05}, 0.30, _cfg(settings))
    assert t["B"] == 0 and t["Z"] == 0


def test_backtest_liquidez_point_in_time():
    idx = pd.bdate_range("2020-01-01", periods=60)
    montos = {"A": pd.Series(100.0, index=idx), "B": pd.Series(np.r_[np.full(40, 10.0), np.full(20, 1000.0)], index=idx)}
    temprano = engine._liquidas_en_fecha(montos, idx[30], set(), 1, 0)
    tarde = engine._liquidas_en_fecha(montos, idx[59], set(), 1, 0)
    assert temprano == ["A"] and tarde == ["B"]   # B recién es la más líquida después: no se usa antes


def test_guia_explica_por_que_se_tienen_las_locales(settings):
    from src.guia import generar_guia
    from src.portfolio.equiponderado import TEXTO_RAZON
    r = _ranking(VOLS)
    r["score"], r["senal"], r["en_cartera"], r["sector"] = 50.0, "NO COMPRAR", False, "bancos"
    o = pd.DataFrame([{"ticker": "A", "lado": "COMPRAR", "cantidad": 10, "monto_ars": 100000.0, "nota": ""}])
    g = generar_guia({"regimen": "neutral"}, {"acciones_ar": 0.3}, {}, "moderado", r, o, estrategia_ar="equiponderado")
    assert TEXTO_RAZON in g


def test_servicio_usa_equiponderado_para_locales_y_score_para_cedears(settings):
    from src.servicio import _targets_rv
    r = _ranking(VOLS)
    r.loc["X", ["tipo", "panel", "liquido", "calidad_datos", "alertas", "vol_ars_20d"]] = \
        ["cedear", "cedears", True, "", "", 1.0]
    r["score"], r["senal"], r["vol_anual"] = 50.0, "NO COMPRAR", 0.2
    r.loc["X", ["score", "senal"]] = [90.0, "COMPRAR"]
    tipos = {t: ("cedear" if t == "X" else "accion") for t in r.index}
    t = _targets_rv(r, {}, dict.fromkeys(r.index, "s"), _cfg(settings), {"acciones_ar": 0.3, "cedears": 0.3}, tipos)
    assert {k for k, w in t.items() if w > 0} == {"A", "B", "C", "X"}


def test_stop_desactivado_no_saca_la_tenida(settings):
    s = _cfg(settings)
    s["estrategia"]["salir_por_stop"] = False
    r = _ranking(VOLS, alertas={"B": "REVISAR STOP: -30% desde el máximo"})
    t = objetivos_equiponderados(r, {"B": 0.1}, 0.30, s)
    assert t["B"] > 0
