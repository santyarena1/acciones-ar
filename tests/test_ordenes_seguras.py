"""Órdenes que no pueden salir mal: caja, montos máximos, cantidad de órdenes, lotes, NaN y validación."""
import math

import pandas as pd
import pytest

from src.portfolio.risk import RiskError, validate_orders
from src.portfolio.rules import generate_orders


def test_compras_no_superan_la_caja_disponible(settings):
    # 100% invertido en A que se vende entero; las ventas liquidan después: no se puede comprar con esa plata
    o = generate_orders({"A": 0.0, "B": 0.5}, {"A": {"cantidad": 1000}}, 100_000, {"A": 1000.0, "B": 100.0}, settings)
    compras = o[o["lado"] == "COMPRAR"]
    costo = (1 + settings["riesgo"]["slippage_limite"]) * (compras["cantidad"] * 100.0).sum()
    assert costo <= 100_000


def test_orden_no_supera_el_monto_maximo_si_esta_configurado(settings):
    s = {**settings, "riesgo": {**settings["riesgo"], "orden_maxima_ars": 2_000_000}}
    o = generate_orders({"A": 0.10}, {}, 100_000_000, {"A": 1000.0}, s)
    assert len(o) == 1 and o.loc[0, "monto_ars"] * (1 + s["riesgo"]["slippage_limite"]) <= 2_000_000
    validate_orders(o, s)  # no levanta


def test_sin_tope_absoluto_la_orden_es_la_que_pide_el_objetivo(settings):
    s = {**settings, "riesgo": {**settings["riesgo"], "orden_maxima_ars": None}}
    o = generate_orders({"A": 0.10}, {}, 100_000_000, {"A": 1000.0}, s)
    assert o.loc[0, "cantidad"] == 10_000
    validate_orders(o, s, valor_total=100_000_000)


def test_orden_no_supera_el_pct_de_cartera(settings):
    s = {**settings, "riesgo": {**settings["riesgo"], "orden_maxima_ars": None, "orden_maxima_pct_cartera": 0.35}}
    o = generate_orders({"A": 0.9}, {}, 1_000_000, {"A": 10.0}, s)   # objetivo absurdo (bug aguas arriba)
    assert o.loc[0, "monto_ars"] * (1 + s["riesgo"]["slippage_limite"]) <= 0.35 * 1_000_000
    validate_orders(o, s, valor_total=1_000_000)


def test_no_genera_mas_ordenes_que_el_maximo_y_prioriza_ventas(settings):
    n = settings["riesgo"]["ordenes_max_por_corrida"]
    targets = {f"T{i}": 0.04 for i in range(n + 5)}
    targets["V"] = 0.0
    precios = {t: 100.0 for t in targets}
    o = generate_orders(targets, {"V": {"cantidad": 1000}}, 10_000_000, precios, settings)
    assert len(o) == n and o.loc[0, "ticker"] == "V"
    validate_orders(o, settings)


def test_lote_minimo_de_bonos(settings):
    o = generate_orders({"ON1": 0.10}, {}, 10_500_000, {"ON1": 100_000.0}, settings,
                        multiplicador={"ON1": 0.01}, lotes={"ON1": 1000})
    assert o.loc[0, "cantidad"] % 1000 == 0


def test_precio_nan_no_genera_orden_ni_rompe(settings):
    o = generate_orders({"A": 0.1}, {}, 1_000_000, {"A": math.nan}, settings)
    assert o.empty


def test_riesgo_rechaza_precio_nan(settings):
    o = pd.DataFrame([{"ticker": "A", "lado": "COMPRAR", "cantidad": 1, "precio_ref": math.nan}])
    with pytest.raises(RiskError):
        validate_orders(o, settings)


def test_riesgo_rechaza_ticker_duplicado(settings):
    o = pd.DataFrame([{"ticker": "A", "lado": "COMPRAR", "cantidad": 1, "precio_ref": 10.0},
                      {"ticker": "A", "lado": "VENDER", "cantidad": 1, "precio_ref": 10.0}])
    with pytest.raises(RiskError):
        validate_orders(o, settings)


def test_riesgo_rechaza_vender_mas_de_lo_que_hay(settings):
    o = pd.DataFrame([{"ticker": "A", "lado": "VENDER", "cantidad": 11, "precio_ref": 10.0}])
    with pytest.raises(RiskError):
        validate_orders(o, settings, posiciones={"A": {"cantidad": 10}})
    validate_orders(o.assign(cantidad=10), settings, posiciones={"A": {"cantidad": 10}})


def test_riesgo_rechaza_compras_por_encima_de_la_caja(settings):
    o = pd.DataFrame([{"ticker": "A", "lado": "COMPRAR", "cantidad": 100, "precio_ref": 1000.0}])
    with pytest.raises(RiskError):
        validate_orders(o, settings, caja_ars=100_000)
    validate_orders(o, settings, caja_ars=110_000)
