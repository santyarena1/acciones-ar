import pandas as pd
import pytest

from src.analysis.scoring import alertas, signal
from src.portfolio.renta_fija_alloc import objetivos_renta_fija
from src.portfolio.risk import validate_orders
from src.portfolio.rules import build_targets, generate_orders


def _scores():
    return pd.DataFrame({
        "score": {"A1": 90, "A2": 80, "C1": 85, "C2": 75, "C3": 70},
        "senal": {"A1": "COMPRAR", "A2": "COMPRAR", "C1": "COMPRAR", "C2": "ESPERAR (sobrecompra)", "C3": "COMPRAR"},
        "liquido": {"A1": True, "A2": True, "C1": True, "C2": True, "C3": True},
        "vol_anual": {"A1": 0.5, "A2": 0.25, "C1": 0.2, "C2": 0.2, "C3": 0.2},
    })


TIPOS = {"A1": "accion", "A2": "accion", "C1": "cedear", "C2": "cedear", "C3": "cedear"}
SECT = {"A1": "bancos", "A2": "energia", "C1": "tecnologia", "C2": "tecnologia", "C3": "salud_ext"}


def test_presupuesto_por_clase_y_respeta_senal(settings):
    t = build_targets(_scores(), {}, SECT, settings, presupuestos={"acciones_ar": 0.15, "cedears": 0.12}, tipos=TIPOS)
    assert t["A1"] + t["A2"] <= 0.15 + 1e-9
    assert t["C1"] + t["C3"] <= 0.12 + 1e-9
    assert t["C2"] == 0          # ESPERAR: no se compra aunque tenga score alto


def test_sizing_por_volatilidad_da_menos_al_mas_volatil(settings):
    s = {**settings, "portfolio": {**settings["portfolio"], "peso_max_accion": 1.0, "peso_max_sector": 1.0}}
    t = build_targets(_scores(), {}, SECT, s, presupuestos={"acciones_ar": 0.3, "cedears": 0.0}, tipos=TIPOS)
    # A1 tiene mejor score pero el doble de volatilidad que A2
    assert t["A2"] > t["A1"]


def test_filtro_tendencia_en_senal(settings):
    assert signal(90, False, 50, settings, True, sobre_sma200=False) == "ESPERAR (tendencia bajista)"
    assert signal(90, True, 50, settings, True, sobre_sma200=False) == "AGREGAR"
    assert signal(90, False, 50, settings, False) == "ILÍQUIDA (no comprar)"


def test_orden_recortada_por_liquidez(settings):
    o = generate_orders({"X": 0.5}, {}, 10_000_000, {"X": 100.0}, settings, vol_ars={"X": 2_000_000})
    tope = int(2_000_000 * settings["liquidez"]["max_pct_volumen_por_orden"] / 100)
    assert o.loc[0, "cantidad"] == tope and o.loc[0, "nota"] == "recortada por liquidez"


def test_bonos_con_multiplicador_y_riesgo(settings):
    # bono a $80.000 cada 100 VN: 10% de $1M = $100.000 -> 125 VN
    o = generate_orders({"AL30": 0.10}, {}, 1_000_000, {"AL30": 80_000.0}, settings, multiplicador={"AL30": 0.01})
    assert o.loc[0, "cantidad"] == 125 and o.loc[0, "monto_ars"] == pytest.approx(100_000)
    v = validate_orders(o, settings)
    assert v.loc[0, "monto_ars"] == pytest.approx(125 * v.loc[0, "precio_limite"] * 0.01)


def test_objetivos_renta_fija():
    rf = pd.DataFrame({"clase": ["soberano_usd"] * 4 + ["lecap"] * 2,
                       "score_rf": [90, 80, 70, 40, 85, 30]}, index=["GD35", "GD30", "AL30", "GD46", "S31L6", "S28N6"])
    t = objetivos_renta_fija(rf, {"bonos_usd": 0.20, "pesos": 0.15}, {}, {"renta_fija": {"peso_max_instrumento": 0.12}})
    assert set(k for k, v in t.items() if v > 0) == {"GD35", "GD30", "AL30", "S31L6"}
    assert t["S31L6"] == 0.12      # tope por instrumento
    assert "GD46" not in t         # score bajo


def test_alertas_stop_solo_en_cartera(settings):
    ind = {"dist_max_52s": -0.4, "close": 8, "sma200": 10, "vol_anual": 0.2}
    assert any("STOP" in a for a in alertas(ind, True, [], settings))
    assert not any("STOP" in a for a in alertas(ind, False, [], settings))
    assert "anunció dividendo" in alertas({}, False, ["dividendo"], settings)
