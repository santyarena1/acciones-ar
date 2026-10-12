"""Capa táctica: eventos, combinación con el perfil, integración con la cartera y backtest (sin red)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.analysis import eventos as ev
from src.analysis import tactico as tc
from src.backtest import tactico as bt
from src.config import load_eventos
from src.guia import _seccion_tactica
from src.portfolio.renta_fija_alloc import objetivos_renta_fija
from src.portfolio.rules import build_targets

BASE = {"acciones_ar": 0.30, "cedears": 0.40, "bonos_usd": 0.15, "pesos": 0.10, "caja": 0.05}
EVENTOS = [{"nombre": "Elección", "fecha": "2027-10-24", "dias_antes": 21, "reduccion_ar": 0.25},
           {"nombre": "Fed", "fecha": "2027-10-20", "dias_antes": 7, "reduccion_ar": 0.0},
           {"nombre": "Roto", "fecha": "no-es-fecha", "dias_antes": 7}]


def test_eventos_ventana_y_reduccion():
    act = ev.eventos_activos(EVENTOS, date(2027, 10, 15))
    assert [e["nombre"] for e in act] == ["Fed", "Elección"] and act[1]["dias_para_evento"] == 9
    assert ev.reduccion_ar(act) == 0.25
    assert ev.eventos_activos(EVENTOS, date(2027, 9, 1)) == [] and ev.reduccion_ar([]) == 0.0
    assert ev.eventos_activos(EVENTOS, date(2027, 10, 25)) == []   # pasó: se vuelve a lo normal
    assert [e["nombre"] for e in ev.proximos(EVENTOS, date(2027, 9, 1), 60)] == ["Fed", "Elección"]


def test_calendario_real_parsea_y_tiene_fuente():
    eventos = load_eventos()
    assert eventos and all(ev._fecha(e["fecha"]) and e.get("fuente") and e.get("confianza") for e in eventos)
    assert all(0 <= float(e.get("reduccion_ar", 0)) <= 1 for e in eventos)


def test_aplicar_tactico_conserva_total_y_mueve_a_refugio():
    a = tc.aplicar_tactico(BASE, 0.5, "neutral", 0.0, {})
    assert sum(a.values()) == pytest.approx(1.0)
    assert a["acciones_ar"] == pytest.approx(0.15) and a["cedears"] == pytest.approx(0.20)
    assert a["bonos_usd"] == pytest.approx(0.15 * 0.75)          # factor 0.5 en régimen normal
    movido = 0.35 + 0.15 * 0.25
    assert a["oro"] == pytest.approx(movido * 0.3, abs=1e-4) and a["pesos"] == pytest.approx(0.10 + movido * 0.5, abs=1e-4)


def test_regimen_adverso_recorta_bonos_entero_y_prefiere_oro():
    a = tc.aplicar_tactico(BASE, 0.5, "adverso", 0.0, {})
    assert a["bonos_usd"] == pytest.approx(0.075) and a["oro"] > a["pesos"] - 0.10


def test_sin_defensivo_ni_eventos_no_cambia_nada():
    a = tc.aplicar_tactico(BASE, 0.0, "neutral", 0.0, {})
    assert {k: v for k, v in a.items() if k != "oro"} == BASE and a["oro"] == 0.0


def test_eventos_bajan_argentina_hacia_cedears_y_caja():
    a = tc.aplicar_tactico(BASE, 0.0, "neutral", 0.5, {})
    assert a["acciones_ar"] == pytest.approx(0.15) and a["bonos_usd"] == pytest.approx(0.075)
    assert a["cedears"] == pytest.approx(0.40 + 0.225 * 0.7) and sum(a.values()) == pytest.approx(1.0)


def test_consolidar_minimos_suma_oro_chico_a_pesos():
    a = tc.consolidar_minimos({"oro": 0.05, "pesos": 0.10}, 500_000, 40_000)
    assert a == {"oro": 0.0, "pesos": 0.15}
    assert tc.consolidar_minimos({"oro": 0.10, "pesos": 0.10}, 500_000, 40_000)["oro"] == 0.10


def _series_crash() -> dict:
    idx = pd.bdate_range("2024-01-01", periods=600)
    spy = pd.Series(np.r_[np.linspace(100, 150, 480), np.linspace(150, 95, 120)], index=idx)
    return {"SPY": spy, "^VIX": pd.Series(38.0, index=idx), "HYG": spy / 2, "IEF": pd.Series(100.0, index=idx),
            "^TNX": pd.Series(4.0, index=idx), "^IRX": pd.Series(5.0, index=idx)}


def _settings_on(settings, rg=True, rot=False, evs=False):
    t = settings["tactico"]
    return {**settings, "tactico": {**t, "riesgo_global": {**t["riesgo_global"], "aplicar": rg},
                                    "rotacion": {**t["rotacion"], "aplicar": rot},
                                    "eventos": {**t["eventos"], "aplicar": evs}}}


def test_resolver_apagado_solo_informa(settings):
    s = _settings_on(settings, rg=False)
    r = tc.resolver_tactico(BASE, "neutral", _series_crash(), {}, EVENTOS, date(2027, 10, 15), s)
    assert r["asignacion"] == BASE and r["defensivo"] == 0.0 and r["defensivo_calculado"] > 0
    assert "apagada" in " ".join(r["motivos"]) and r["refugio_oro"] is None
    assert r["eventos"] and r["reduccion_eventos"] == 0.0


def test_resolver_prendido_pasa_a_refugio(settings):
    s = _settings_on(settings, rg=True, evs=True)
    r = tc.resolver_tactico(BASE, "neutral", _series_crash(), {}, EVENTOS, date(2027, 10, 15), s)
    assert r["defensivo"] == pytest.approx(0.8) and r["asignacion"]["oro"] > 0
    assert r["asignacion"]["acciones_ar"] < BASE["acciones_ar"] * 0.3 and r["reduccion_eventos"] == 0.25
    assert r["refugio_oro"] == "GLD" and r["clases_pesos"] == ["lecap", "boncap"]
    assert "paso 80% de las acciones a refugio" in " ".join(r["motivos"])
    assert sum(r["asignacion"].values()) == pytest.approx(1.0, abs=1e-3)


def test_mult_rotacion_escala_el_tamano(settings):
    sc = pd.DataFrame({"score": {"C1": 80, "C2": 80}, "senal": {"C1": "COMPRAR", "C2": "COMPRAR"},
                       "liquido": {"C1": True, "C2": True}, "vol_anual": {"C1": 0.2, "C2": 0.2},
                       "mult_rotacion": {"C1": 1.5, "C2": 0.5}})
    s = {**settings, "portfolio": {**settings["portfolio"], "peso_max_accion": 1.0, "peso_max_sector": 1.0}}
    t = build_targets(sc, {}, {"C1": "a", "C2": "b"}, s, presupuestos={"cedears": 0.4},
                      tipos={"C1": "cedear", "C2": "cedear"})
    assert t["C1"] == pytest.approx(0.3, abs=1e-3) and t["C2"] == pytest.approx(0.1, abs=1e-3)


def test_pesos_restringidos_a_letras_vende_cer():
    rf = pd.DataFrame({"clase": ["lecap", "cer", "boncap"], "score_rf": [70, 90, 60]}, index=["S1", "TX1", "T1"])
    s = {"renta_fija": {"peso_max_instrumento": 0.5, "clases_pesos": ["lecap", "boncap"]}}
    t = objetivos_renta_fija(rf, {"pesos": 0.2}, {"TX1": 0.05}, s)
    assert t["TX1"] == 0.0 and t["S1"] > 0 and t["T1"] > 0


def test_servicio_oro_es_refugio_y_no_se_elige_por_score(settings):
    from src.servicio import _aplicar_tactico_cartera, _objetivo_oro
    ranking = pd.DataFrame({"score": {"GLD": 20, "AAPL": 80}, "calidad_datos": {"GLD": "", "AAPL": ""}})
    tac = {"refugio_oro": "GLD", "mult_por_ticker": {"AAPL": 1.2}, "clases_pesos": ["lecap"]}
    asig = {**BASE, "oro": 0.10}
    tac2, asig2, rk, clases, s2, oro = _aplicar_tactico_cartera(tac, asig, 1_000_000, ranking, {"GLD": "cedears"},
                                                               settings)
    assert oro == "GLD" and clases["GLD"] == "oro" and rk.at["AAPL", "mult_rotacion"] == 1.2
    assert s2["renta_fija"]["clases_pesos"] == ["lecap"] and "clases_pesos" not in settings["renta_fija"]
    assert _objetivo_oro(oro, asig2, ranking, {}) == {"GLD": 0.10}
    roto = ranking.assign(calidad_datos=["precio viejo", ""])
    assert _objetivo_oro(oro, asig2, roto, {"GLD": 0.03}) == {"GLD": 0.03}


def test_guia_explica_la_capa_tactica():
    tac = {"riesgo": 0.7, "motivos": ["El S&P 500 está debajo de su tendencia: paso 40% a refugio."],
           "asignacion_base": BASE, "asignacion": {**BASE, "cedears": 0.2, "oro": 0.2}}
    txt = "\n".join(_seccion_tactica(tac))
    assert "riesgo global 70%" in txt and "Oro (refugio) 0% → 20%" in txt
    assert _seccion_tactica(None) == []


# --- backtest ---------------------------------------------------------------------------------------

def test_bono_sintetico_cae_si_sube_el_riesgo_pais_e_ignora_quiebres():
    idx = pd.date_range("2020-01-01", periods=5)
    tnx = pd.Series(4.0, index=idx)
    sube = bt.bono_sintetico(pd.Series([500, 500, 1200, 1200, 1200.0], index=idx), tnx)
    assert sube.iloc[2] < sube.iloc[1] * 0.8
    quiebre = bt.bono_sintetico(pd.Series([2100, 2100, 1100, 1100, 1100.0], index=idx), tnx)
    assert quiebre.iloc[2] == pytest.approx(quiebre.iloc[1] * (1 + 0.25 / 365), rel=1e-6)


def test_indice_tasa_y_fechas_decision():
    idx = pd.bdate_range("2021-01-01", periods=70)
    t = bt.indice_tasa(pd.Series(3.65, index=idx))
    assert t.iloc[-1] > 1 and t.is_monotonic_increasing
    f = bt.fechas_decision(idx, "ME", "2021-01-01")
    assert [d.month for d in f] == [1, 2, 3, 4] and f[0] == pd.Timestamp("2021-01-29")


def _datos_bt(settings):
    idx = pd.bdate_range("2015-01-01", periods=900)
    rng = np.random.default_rng(0)
    px = lambda d, s: pd.Series(100 * np.exp(np.cumsum(d + rng.normal(0, 0.01, 900))), index=idx)  # noqa: E731
    p = {t: px(0.0004, i) for i, t in enumerate(["GGAL", "YPF", "SPY", "XLK", "XLE", "EEM", "GLD", "HYG", "IEF"])}
    p.update({"^VIX": pd.Series(15.0, index=idx), "^TNX": pd.Series(3.0, index=idx), "^IRX": pd.Series(1.0, index=idx)})
    grupos = {"g1": {"proxy": "XLK"}, "g2": {"proxy": "XLE"}, "g3": {"proxy": "EEM"}, "g4": {"proxy": "SPY"}}
    return bt.preparar(p, pd.Series(600.0, index=idx), None, None, grupos)


def test_simular_perfil_fijo_y_variantes(settings):
    d = _datos_bt(settings)
    fijo = bt.simular(d, settings, "moderado_agresivo", {}, desde="2016-01-01")
    todo = bt.simular(d, settings, "moderado_agresivo", {"ar_regimen": True, "global": True, "rotacion": True},
                      desde="2016-01-01")
    assert len(fijo["curva"]) > 20 and fijo["curva"].iloc[-1] > 0 and todo["curva"].iloc[-1] > 0
    cl = fijo["clases"]
    assert (cl[["acciones_ar", "cedears", "bonos_usd", "pesos", "caja", "oro"]].astype(float).sum(axis=1)
            .sub(1).abs() < 1e-3).all()
    m = bt.metricas(fijo["curva"], 12)
    assert set(m) == {"cagr", "vol", "sharpe", "max_dd", "calmar"} and m["max_dd"] <= 0


def test_estudio_eventos_mide_ventana_y_reaccion():
    idx = pd.bdate_range("2019-07-01", periods=40)
    s = pd.Series(100.0, index=idx)
    s[s.index >= "2019-08-12"] = 50.0
    e = bt.estudio_eventos(s, ["2019-08-11"], 10, 1)
    assert e.loc[0, "reaccion"] == pytest.approx(-0.5) and e.loc[0, "ventana_previa"] == pytest.approx(0.0)
