"""Histéresis de señales y construcción de cartera sin rotación innecesaria."""
import pandas as pd
import pytest

from src.analysis.scoring import signal
from src.portfolio.rules import build_targets


def _cfg(settings, **portfolio):
    s = {**settings, "umbrales": {**settings["umbrales"], "histeresis": 3}}
    s["portfolio"] = {**settings["portfolio"], **portfolio}
    return s


def test_no_tenida_compra_solo_con_margen(settings):
    s = _cfg(settings)
    c = s["umbrales"]["comprar"]
    assert signal(c + 1, False, 50, s, True, True) == "NO COMPRAR"
    assert signal(c + 3, False, 50, s, True, True) == "COMPRAR"


def test_tenida_vende_solo_con_margen(settings):
    s = _cfg(settings)
    v = s["umbrales"]["vender"]
    assert signal(v - 1, True, 50, s, True, True) == "MANTENER"
    assert signal(v - 3.5, True, 50, s, True, True) == "REDUCIR / VENDER"
    assert signal(s["umbrales"]["comprar"], True, 50, s, True, False) == "AGREGAR"  # bajo SMA200 no vende


def test_no_tenida_sin_sma200_conocida_no_abre_posicion(settings):
    assert signal(90, False, 50, _cfg(settings), True, None).startswith("ESPERAR")


def test_tenida_cerca_del_umbral_de_venta_no_se_vende_en_cartera(settings):
    s = _cfg(settings)
    v = s["umbrales"]["vender"]
    sc = pd.DataFrame({"score": {"H": v - 1}, "liquido": {"H": True}})
    t = build_targets(sc, {"H": 0.05}, {"H": "x"}, s)
    assert t["H"] == pytest.approx(0.05)


def test_tenida_con_buen_score_no_se_recorta_por_falta_de_presupuesto(settings):
    # 4 posiciones "mantener" ocupan casi toda la clase; la mejor (AGREGAR) no puede quedar más chica que hoy
    s = _cfg(settings, peso_max_sector=1.0)
    sc = pd.DataFrame({
        "score": {"M1": 55, "M2": 55, "M3": 55, "TOP": 90, "NEW": 85},
        "senal": {"M1": "MANTENER", "M2": "MANTENER", "M3": "MANTENER", "TOP": "AGREGAR", "NEW": "COMPRAR"},
        "liquido": dict.fromkeys(["M1", "M2", "M3", "TOP", "NEW"], True),
    })
    act = {"M1": 0.08, "M2": 0.08, "M3": 0.08, "TOP": 0.08}
    tipos = dict.fromkeys(sc.index, "accion")
    t = build_targets(sc, act, {k: k for k in sc.index}, s, presupuestos={"acciones_ar": 0.36, "cedears": 0.0},
                      tipos=tipos)
    assert t["TOP"] >= 0.08 - 1e-4
    assert sum(t.values()) <= 0.36 + 1e-9


def test_tope_de_sector_redistribuye_y_no_deja_caja_ociosa(settings):
    s = _cfg(settings, peso_max_accion=0.10, peso_max_sector=0.10, max_posiciones_rv=10)
    sc = pd.DataFrame({"score": {"B1": 90, "B2": 90, "E1": 80, "E2": 80}, "liquido": dict.fromkeys(
        ["B1", "B2", "E1", "E2"], True)})
    sect = {"B1": "bancos", "B2": "bancos", "E1": "energia", "E2": "utilities"}
    t = build_targets(sc, {}, sect, s, presupuestos={"acciones_ar": 0.30, "cedears": 0.0},
                      tipos=dict.fromkeys(sc.index, "accion"))
    assert t["B1"] + t["B2"] <= 0.10 + 1e-9
    assert sum(t.values()) == pytest.approx(0.30, abs=1e-3)   # lo que no entra en bancos va a los otros


def test_tope_de_sector_recorta_primero_lo_nuevo_y_no_lo_que_ya_tengo(settings):
    s = _cfg(settings, peso_max_accion=0.10, peso_max_sector=0.12)
    sc = pd.DataFrame({"score": {"H": 55, "N": 90}, "senal": {"H": "MANTENER", "N": "COMPRAR"},
                       "liquido": {"H": True, "N": True}})
    t = build_targets(sc, {"H": 0.08}, {"H": "bancos", "N": "bancos"}, s,
                      presupuestos={"acciones_ar": 0.30, "cedears": 0.0}, tipos={"H": "accion", "N": "accion"})
    assert t["H"] == pytest.approx(0.08) and t["N"] == pytest.approx(0.04)


def test_posicion_sin_datos_no_se_toca_ni_por_tope(settings):
    # Z está en cartera pero no en el universo (o sin precios): no se vende nada sin datos; ocupa presupuesto
    sc = pd.DataFrame({"score": {"A": 90.0, "N": float("nan")}, "liquido": {"A": True, "N": True}})
    t = build_targets(sc, {"Z": 0.15, "N": 0.12}, {"A": "x"}, settings,
                      presupuestos={"acciones_ar": 0.30, "cedears": 0.0}, tipos={"A": "accion", "N": "accion"})
    assert "Z" not in t and "N" not in t
    assert t["A"] <= 0.30 - 0.27 + 1e-9
