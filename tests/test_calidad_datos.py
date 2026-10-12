"""Calidad de datos: caché con TTL, precios viejos, saltos, picos, ruedas cerradas, CEDEARs y fundamentales."""
import os
import time
from datetime import date, datetime
from datetime import time as dtime

import numpy as np
import pandas as pd
import pytest

from src.data import prices as pr
from src.data.fundamentals import from_yf_info, sanear
from src.pipeline import _scores_fundamentales, analyze
from tests.conftest import serie

CFG = {"max_dias_sin_precio": 3, "max_salto_diario": 0.25, "ruedas_sin_volumen_max": 3}


def _ars(closes, vols=None, fin="2026-10-09"):
    idx = pd.bdate_range(end=fin, periods=len(closes))
    return pd.DataFrame({"close": closes, "volume": vols or [1000] * len(closes)}, index=idx)


def test_cache_con_ttl_vence_a_los_n_minutos(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a")
    viejo = time.time() - 20 * 60
    os.utime(p, (viejo, viejo))
    assert pr._cache_fresca(p, ttl_min=None)          # sin TTL: vale todo el día
    assert not pr._cache_fresca(p, ttl_min=15)        # con TTL de 15': hay que volver a bajar
    assert pr._cache_fresca(p, ttl_min=30)


def test_cache_corta_no_sirve_para_un_pedido_mas_largo(tmp_path, monkeypatch):
    # el backtest pide desde 2018 después de que `analizar` cacheó solo 3 años: no puede usar la caché corta
    monkeypatch.setattr(pr, "CACHE_DIR", tmp_path)
    corto = _ars([10.0] * 50, fin="2026-10-09")
    pr._guardar_cache(corto, pr._cache_path("yf_AAA.BA"))
    pedidos = []
    monkeypatch.setattr(pr, "_yf_lote", lambda s, d: pedidos.extend(s) or {})
    pr.load_many(["AAA.BA"], date(2018, 1, 1))
    assert pedidos == ["AAA.BA"]


def test_precio_viejo_se_marca():
    df = _ars([10.0] * 30, fin="2026-09-25")
    assert "sin precio" in pr.diagnostico_calidad(df, date(2026, 10, 9), CFG)
    assert pr.diagnostico_calidad(_ars([10.0] * 30), date(2026, 10, 9), CFG) == ""


def test_salto_implausible_en_la_ultima_rueda_se_marca():
    df = _ars([10.0] * 29 + [14.0])
    assert "salto" in pr.diagnostico_calidad(df, date(2026, 10, 9), CFG)


def test_sin_operaciones_recientes_se_marca():
    df = _ars([10.0] * 30, vols=[1000] * 26 + [0, 0, 0, 0])
    assert "sin operaciones" in pr.diagnostico_calidad(df, date(2026, 10, 9), CFG)


def test_pico_de_un_dia_que_revierte_se_limpia():
    df = _ars([300.0, 304.0, 184.0, 296.0, 302.0, 305.0])  # print malo de CELU (feb-2026)
    limpio = pr.limpiar_picos(df, 0.30)
    assert 184.0 not in limpio["close"].values and len(limpio) == 5
    # una caída que NO revierte es real y se conserva
    real = _ars([300.0, 304.0, 184.0, 186.0, 185.0])
    assert len(pr.limpiar_picos(real, 0.30)) == 5


def test_rueda_de_hoy_incompleta_no_entra_al_analisis():
    df = _ars([10.0, 11.0, 12.0], fin="2026-10-09")
    antes = pr.ruedas_cerradas(df, datetime(2026, 10, 9, 13, 0), dtime(18, 0))
    despues = pr.ruedas_cerradas(df, datetime(2026, 10, 9, 18, 30), dtime(18, 0))
    assert len(antes) == 2 and len(despues) == 3


def test_volumen_con_poca_historia_no_cuenta_como_liquido():
    assert pr.volumen_ars_promedio(_ars([100.0], vols=[10**6])) is None


def test_ccl_implicito_de_cedear_desfasado_se_detecta():
    idx = pd.bdate_range(end="2026-10-09", periods=25)
    ccl = pd.Series(1500.0, index=idx)
    usd = pd.Series(100.0, index=idx)
    ars = usd * 1500 / 20  # ratio 20
    assert abs(pr.desvio_ratio_cedear(ars, usd, ccl)) < 1e-9
    ars_viejo = ars.copy()
    ars_viejo.iloc[-1] *= 0.90  # el CEDEAR quedó 10% abajo del subyacente (precio viejo o ratio cambiado)
    assert pr.desvio_ratio_cedear(ars_viejo, usd, ccl) == pytest.approx(1 / 0.9 - 1)


def test_fundamentales_absurdos_se_descartan():
    m = sanear({"pe": 8.0, "ev_ebitda": 7332.7, "pb": 0.000987, "roe": 0.15, "revenue_growth": 7.18,
                "operating_margin": 0.2, "net_debt_ebitda": 1.0, "fcf_yield": 0.05})
    assert m["ev_ebitda"] is None and m["pb"] is None and m["revenue_growth"] is None
    assert m["pe"] == 8.0 and m["roe"] == 0.15


def test_pe_faltante_con_perdidas_cuenta_como_perdidas():
    assert sanear({"pe": None, "roe": -0.2})["pe"] < 0


def test_moneda_de_balance_distinta_descarta_ratios_de_precio():
    info = {"trailingPE": 8.4, "enterpriseToEbitda": 7332.0, "priceToBook": 1.1, "returnOnEquity": 0.15,
            "freeCashflow": 10.0, "marketCap": 1e6, "currency": "ARS", "financialCurrency": "USD"}
    m = from_yf_info(info)
    assert m["ev_ebitda"] is None and m["pb"] is None and m["fcf_yield"] is None
    assert m["pe"] == 8.4 and m["roe"] == 0.15


def test_crecimiento_nominal_en_pesos_no_suma_en_el_absoluto_de_locales(settings):
    uni = [{"ticker": "LOC", "tipo": "accion", "sector": "utilities", "panel": "lider"}]
    base = {"pe": 10, "roe": 0.1, "operating_margin": 0.1, "pb": 1.0}
    a = _scores_fundamentales({"LOC": {**base, "revenue_growth": 0.9}}, uni, settings)
    b = _scores_fundamentales({"LOC": {**base, "revenue_growth": -0.05}}, uni, settings)
    assert a.at["LOC", "fund_abs"] == b.at["LOC", "fund_abs"]


def _uni(t="X", tipo="accion"):
    return [{"ticker": t, "tipo": tipo, "sector": "energia", "panel": "lider"}]


def test_datos_dudosos_no_compra_ni_vende(settings):
    precios = {"X": serie(0.003, n=400)}
    r = analyze(precios, {}, _uni(), settings, "corto", set(), {"X": 1e9}, calidad={"X": "precio viejo"})
    assert r.at["X", "senal"].startswith("DATOS DUDOSOS")
    r2 = analyze(precios, {}, _uni(), settings, "corto", {"X"}, {"X": 1e9}, calidad={"X": "precio viejo"})
    assert r2.at["X", "senal"].startswith("MANTENER")


def test_sin_historia_de_precios_nunca_es_compra(settings):
    fund = {"X": {"pe": 5, "ev_ebitda": 3, "pb": 0.5, "roe": 0.3, "operating_margin": 0.3,
                  "net_debt_ebitda": 0.0, "fcf_yield": 0.15, "revenue_growth": 0.2}}
    r = analyze({}, fund, _uni(), settings, "largo", set(), {"X": 1e9})
    assert r.at["X", "senal"] not in ("COMPRAR", "AGREGAR")
    assert not np.isnan(r.at["X", "score"])


def test_si_falla_la_descarga_se_usa_la_cache_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "CACHE_DIR", tmp_path)
    df = _ars([10.0] * 50, fin="2026-10-09")
    p = pr._cache_path("yf_AAA.BA")
    pr._guardar_cache(df, p)
    viejo = time.time() - 3600
    os.utime(p, (viejo, viejo))
    monkeypatch.setattr(pr, "_yf_lote", lambda s, d: {})       # yfinance no devolvió nada
    out = pr.load_many(["AAA.BA"], df.index[0].date(), ttl_min=15)
    assert "AAA.BA" in out and len(out["AAA.BA"]) == 50


def test_limites_de_settings_como_texto_no_rompen():
    assert sanear({"pe": 10.0}, {"pe": ("-1.0e9", "300")})["pe"] == 10.0


class _P:
    def __init__(self, ccl):
        self.ultimo_ars, self.ccl = {}, ccl


def test_posicion_en_dolares_se_valua_en_pesos():
    from src.servicio import _precios_y_mult
    ccl = pd.Series([1500.0, 1600.0], index=pd.bdate_range(end="2026-10-09", periods=2))
    pos = {"ONUSD": {"cantidad": 1000, "precio": 101.0, "tipo": "on", "moneda": "USD"},
           "RARA": {"cantidad": 1000, "precio": 99.0, "tipo": "on", "moneda": "ARS", "unidad_dudosa": True},
           "GGAL": {"cantidad": 10, "precio": 7000.0, "tipo": "accion", "moneda": "ARS"}}
    px, mult = _precios_y_mult(_P(ccl), pd.DataFrame(), pos)
    assert px["ONUSD"] == pytest.approx(101.0 * 1600) and mult["ONUSD"] == 0.01
    assert "RARA" not in px          # unidad dudosa: no se valúa (ni se opera) con un precio que puede estar x100
    assert px["GGAL"] == 7000.0


def test_descarga_sin_columna_close_no_rompe_la_corrida():
    raro = pd.DataFrame({"Volume": [1, 2]}, index=pd.bdate_range("2026-10-01", periods=2))
    assert pr._normalizar_yf(raro).empty
