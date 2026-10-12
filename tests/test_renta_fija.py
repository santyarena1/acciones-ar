"""Tests de renta fija: matemática pura, cronogramas, parsers (fixtures, sin red) y análisis."""
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.renta_fija import analisis, calculos as c, datos, parsers, servicio, valuacion
from src.renta_fija.calculos import Flujo
from src.renta_fija.flujos import cuotas_amortizacion, fechas_periodicas, generar_flujos, sumar_meses

FIX = Path(__file__).parent / "fixtures"
FERIADOS = {date(2026, 10, 12), date(2026, 11, 23)}


def fixture(nombre: str):
    return json.loads((FIX / nombre).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cfg():
    return datos.cargar_config()


@pytest.fixture(scope="module")
def cotiz():
    filas = fixture("rf_data912_bonds.json") + fixture("rf_data912_notes.json") + fixture("rf_data912_corp.json")
    return parsers.parsear_data912(filas)


# ----------------------------------------------------------------------------- matemática pura

def test_tir_bullet_calculable_a_mano():
    # paga 110 en exactamente 365 días y cuesta 100 -> 10% efectivo anual
    assert c.xirr([(date(2026, 1, 1), 110.0)], 100.0, date(2025, 1, 1)) == pytest.approx(0.10, abs=1e-9)


def test_tir_bono_con_cupon_a_la_par_es_el_cupon():
    liq = date(2025, 1, 1)
    flujos = [Flujo(date(2026, 1, 1), 5.0, 0.0), Flujo(date(2027, 1, 1), 5.0, 100.0)]
    assert c.tir_flujos(flujos, 100.0, liq) == pytest.approx(0.05, abs=1e-6)


def test_tir_sin_flujos_futuros_o_precio_invalido_es_none():
    assert c.xirr([(date(2020, 1, 1), 100.0)], 90.0, date(2025, 1, 1)) is None
    assert c.xirr([(date(2026, 1, 1), 100.0)], 0.0, date(2025, 1, 1)) is None


def test_tem_de_lecap():
    assert c.tem_cupon_cero(100.0, 103.0, 30) == pytest.approx(0.03)
    assert c.tem_cupon_cero(100.0, 103.0, 0) is None
    tem = c.tem_cupon_cero(134.075, 135.278, 17)
    assert c.tem_desde_tea(c.tea_desde_tem(tem)) == pytest.approx(tem)
    assert c.tna_simple(100.0, 102.0, 73) == pytest.approx(0.10)


def test_pago_final_desde_tea_inverso_de_la_tir():
    pago = c.pago_final_desde_tea(100.0, 0.25, 200)
    assert c.xirr([(date(2026, 1, 1) + pd.Timedelta(days=200).to_pytimedelta(), pago)], 100.0,
                  date(2026, 1, 1)) == pytest.approx(0.25, abs=1e-9)


def test_duration_y_convexidad_de_un_cupon_cero():
    liq, venc = date(2025, 1, 1), date(2027, 1, 1)  # 730 días = 2 años
    pagos, r = [(venc, 100.0)], 0.08
    assert c.duration_macaulay(pagos, liq, r) == pytest.approx(2.0)
    assert c.duration_modificada(pagos, liq, r) == pytest.approx(2.0 / 1.08)
    assert c.convexidad(pagos, liq, r) == pytest.approx(2.0 * 3.0 / 1.08 ** 2)


def test_residual_cupon_corrido_y_paridad():
    flujos = [Flujo(date(2025, 1, 9), 1.0, 50.0), Flujo(date(2025, 7, 9), 0.5, 50.0)]
    liq = date(2025, 4, 9)  # mitad aprox. del segundo semestre
    assert c.valor_residual(flujos, liq) == 50.0
    corrido = c.interes_corrido(flujos, liq, date(2024, 7, 9))
    assert corrido == pytest.approx(0.5 * 90 / 181)
    assert c.paridad(45.0, 50.0 + corrido) == pytest.approx(45.0 / (50.0 + corrido))
    assert c.paridad(45.0, 0.0) is None


def test_dias_habiles_y_liquidacion_t_mas_1():
    assert c.sumar_dias_habiles(date(2026, 10, 9), 1, FERIADOS) == date(2026, 10, 13)
    assert c.sumar_dias_habiles(date(2026, 10, 13), -1, FERIADOS) == date(2026, 10, 9)
    assert c.fecha_liquidacion(date(2026, 10, 8), FERIADOS) == date(2026, 10, 9)
    # domingo + lunes feriado: precios del viernes, liquidan el martes
    assert c.fecha_liquidacion(date(2026, 10, 11), FERIADOS) == date(2026, 10, 13)


def test_tasa_real_fisher():
    assert c.tasa_real(0.03, 0.02) == pytest.approx(1.03 / 1.02 - 1)


# ----------------------------------------------------------------------------- cronogramas

def test_sumar_meses_y_fechas_periodicas():
    assert sumar_meses(date(2025, 8, 31), 6) == date(2026, 2, 28)
    fechas = fechas_periodicas(date(2021, 7, 9), date(2023, 1, 9), 6)
    assert fechas == [date(2021, 7, 9), date(2022, 1, 9), date(2022, 7, 9), date(2023, 1, 9)]


def test_cuotas_amortizacion_con_primera_distinta():
    pagos = fechas_periodicas(date(2024, 7, 9), date(2030, 7, 9), 6)
    cuotas = cuotas_amortizacion({"inicio": date(2024, 7, 9), "cuotas": 13, "primera_pct": 4.0}, pagos)
    assert cuotas[date(2024, 7, 9)] == 4.0 and cuotas[date(2030, 7, 9)] == 8.0
    assert sum(cuotas.values()) == pytest.approx(100.0)
    with pytest.raises(ValueError):
        cuotas_amortizacion({"inicio": date(2024, 7, 9), "cuotas": 40}, pagos)


def test_cronograma_gd30_step_up(cfg):
    flujos = generar_flujos(cfg["instrumentos"]["GD30"])
    por_fecha = {f.fecha: f for f in flujos}
    assert sum(f.amortizacion for f in flujos) == pytest.approx(100.0)
    assert c.valor_residual(flujos, date(2026, 10, 13)) == pytest.approx(64.0)
    assert por_fecha[date(2026, 7, 9)].interes == pytest.approx(72 * 0.0075 / 2)  # 0,75% sobre 72
    assert por_fecha[date(2028, 1, 9)].interes == pytest.approx(48 * 0.0175 / 2)  # sube a 1,75% en jul-27


def test_cronogramas_canje_2020_cierran_en_100(cfg):
    for t in ("GD29", "GD30", "GD35", "GD38", "GD41", "GD46", "AL29", "AL30", "AL35", "AE38", "AL41"):
        flujos = generar_flujos(cfg["instrumentos"][t])
        assert sum(f.amortizacion for f in flujos) == pytest.approx(100.0), t
        assert flujos[-1].fecha == cfg["instrumentos"][t]["vencimiento"], t


@pytest.mark.parametrize("ticker,precio,tir_reporte", [
    ("GD30", 57.86, 0.0678), ("AL30", 55.47, 0.0908), ("GD35", 78.09, 0.0984),
    ("AE38", 76.89, 0.1119), ("GD41", 72.89, 0.0989), ("AN29", 92.20, 0.1043), ("TY30P", 111.25, 0.3031),
])
def test_tir_coincide_con_reporte_gorostiaga(cfg, ticker, precio, tir_reporte):
    # precios BYMA del 18/09/2026 (liquidación 21/09) del Reporte Semanal n°212, figs. 7 y 11
    tir = c.tir_flujos(generar_flujos(cfg["instrumentos"][ticker]), precio, date(2026, 9, 21))
    assert tir == pytest.approx(tir_reporte, abs=0.0015)


def test_todos_los_instrumentos_del_yaml_tienen_fuente_y_flujos(cfg):
    for t, term in cfg["instrumentos"].items():
        assert term.get("fuente") and term.get("confianza") in {"alta", "media", "baja"}, t
        assert term["clase"] in {"soberano_usd", "lecap", "boncap", "cer", "dual", "on_usd"}, t
        assert generar_flujos(term), t


# ----------------------------------------------------------------------------- parsers

def test_parser_data912(cotiz):
    assert {"GD30", "GD30D", "S13N6", "YM34D"} <= set(cotiz.index)
    assert cotiz.loc["GD30D", "ultimo"] == 57.67 and cotiz.loc["GD30D", "volumen_nominal"] > 0
    with pytest.raises(ValueError):
        parsers.parsear_data912({"no": "lista"})


def test_precio_referencia():
    assert parsers.precio_referencia(10, 12, 11.5) == 11.5
    assert parsers.precio_referencia(10, 12, 0) == 11
    assert parsers.precio_referencia(None, 12, None) == 12
    assert parsers.precio_referencia(None, None, None) is None


def test_parser_letras_argentinadatos():
    df = parsers.parsear_letras_argentinadatos(fixture("rf_ad_letras.json"))
    s13 = df.set_index("ticker").loc["S13N6"]
    assert s13["vencimiento"] == date(2026, 11, 13) and s13["tea"] == pytest.approx(0.256)
    with pytest.raises(ValueError):
        parsers.parsear_letras_argentinadatos({"otra": []})


def test_parser_cer_y_feriados():
    cer = parsers.parsear_cer_bcra(fixture("rf_bcra_cer.json"))
    assert cer[date(2026, 10, 1)] > cer[date(2026, 9, 1)] > 800
    fer = parsers.parsear_feriados(fixture("rf_feriados_2026.json"))
    assert date(2026, 10, 12) in fer
    with pytest.raises(ValueError):
        parsers.parsear_cer_bcra({"results": []})


def test_parser_tablas_gorostiaga():
    df = parsers.parsear_tablas_gorostiaga((FIX / "rf_gorostiaga_tablas.txt").read_text(encoding="utf-8"))
    gd30 = df.set_index("ticker").loc["GD30"]
    assert gd30["vencimiento"] == date(2030, 7, 9) and gd30["precio"] == 57.86 and gd30["tir"] == pytest.approx(0.0678)
    assert {"AL35", "TX26", "TZXD6", "S13N6", "TY30P"} <= set(df["ticker"])
    assert len(df) == 10  # las líneas de encabezado no se parsean


# ----------------------------------------------------------------------------- valuación

def _ctx(cer_ref=846.33537355394, mep=1540.0):
    return valuacion.Contexto(date(2026, 10, 13), cer_ref, mep, 0.02, 0.01)


def test_mep_implicito(cotiz):
    assert valuacion.mep_implicito(cotiz) == pytest.approx(1540, rel=0.01)


def test_evaluar_lecap_soberano_cer_y_on(cfg, cotiz):
    ins = cfg["instrumentos"]
    lecap = valuacion.evaluar("S13N6", ins["S13N6"], cotiz, _ctx())
    assert lecap["tem"] == pytest.approx(c.tem_desde_tea(c.tea_desde_tem(c.tem_cupon_cero(107.549, 109.65, 31))))
    assert lecap["duration"] == pytest.approx(31 / 365 / (1 + lecap["tir"]))
    gd30 = valuacion.evaluar("GD30", ins["GD30"], cotiz, _ctx())
    assert gd30["precio"] == 57.67 and gd30["precio_ars"] == 88750.0 and gd30["ticker_iol_usd"] == "GD30D"
    assert 0.06 < gd30["tir"] < 0.09 and gd30["residual"] == pytest.approx(64.0)
    cer = valuacion.evaluar("TZXD6", ins["TZXD6"], cotiz, _ctx())
    assert cer["tipo_tasa"] == "real_cer" and cer["paridad"] == pytest.approx(311.1 / (100 * 846.335 / 271.0476), rel=1e-4)
    sin_cer = valuacion.evaluar("TZXD6", ins["TZXD6"], cotiz, _ctx(cer_ref=None))
    assert sin_cer["tir"] is None
    on = valuacion.evaluar("YM34", ins["YM34"], cotiz, _ctx())
    assert on["ticker_iol"] == "YM34O" and on["clase"] == "on_usd" and on["tir"] > 0


def test_evaluar_instrumento_vencido_devuelve_none(cotiz):
    term = {"clase": "lecap", "moneda": "ARS", "vencimiento": date(2026, 1, 1), "pago_final": 110}
    assert valuacion.evaluar("S01E6", term, cotiz, _ctx()) is None


def test_terminos_dinamicos_completa_letras_nuevas():
    letras = parsers.parsear_letras_argentinadatos(fixture("rf_ad_letras.json"))
    nuevos = valuacion.terminos_dinamicos(letras, {"S13N6": {}})
    assert "S30N6" in nuevos and "T15E7" in nuevos
    assert "S13N6" not in nuevos and "TTD26" not in nuevos and "TO26" not in nuevos  # conocido, dual y Bonte
    assert nuevos["S30N6"]["pago_final"] == pytest.approx(129.888, abs=0.01)


def test_carries():
    ctx = _ctx()
    real, usd = valuacion.carries("lecap", 0.40, ctx)  # mes calendario = 1/12 de año
    mensual = 1.40 ** (1 / 12)
    assert real == pytest.approx(mensual / 1.02 - 1) and usd == pytest.approx(mensual / 1.01 - 1)
    real_cer, _ = valuacion.carries("cer", 0.0, ctx)
    assert real_cer == pytest.approx(0.0)
    assert valuacion.carries("cer", None, ctx) == (None, None)


def test_cer_referencia_usa_rezago_habil():
    serie = {date(2026, 9, 28): 1.0, date(2026, 9, 29): 2.0, date(2026, 9, 30): 3.0}
    # liquidación 13/10 - 10 hábiles (12/10 feriado) = 28/09
    assert servicio.cer_referencia(serie, date(2026, 10, 13), 10, FERIADOS) == 1.0
    assert servicio.cer_referencia({}, date(2026, 10, 13), 10, FERIADOS) is None


# ----------------------------------------------------------------------------- análisis

def _tabla(**extra) -> pd.DataFrame:
    base = {
        "ticker": ["A1", "A2", "A3", "A4", "A5", "C1", "C2", "C3", "F1"],
        "clase": ["soberano_usd"] * 5 + ["cer"] * 3 + ["lecap"],
        "familia": ["global"] * 5 + ["cer"] * 3 + ["tasa_fija"],
        "tipo_tasa": ["usd"] * 5 + ["real_cer"] * 3 + ["nominal_ars"],
        "tir": [0.08, 0.09, 0.10, 0.11, 0.12, 0.05, 0.05, 0.05, 0.30],
        "duration": [1.0, 2.0, 3.0, 4.0, 5.0, 0.5, 1.0, 2.0, 0.5],
        "dias": [400, 800, 1200, 1600, 2000, 200, 400, 800, 200],
        "par": [None] * 9, "ley": ["NY"] * 5 + [None] * 4,
        "volumen_ars": [1e9, 1e7, 5e9, 1e5, 2e9, 1e8, 1e8, 1e8, 1e10],
        "carry_usd": [0.006, 0.007, 0.008, 0.009, 0.010, 0.010, 0.010, 0.010, 0.011],
    }
    return pd.DataFrame({**base, **extra})


def test_curva_nelson_siegel_recupera_curva_plana_y_log_con_pocos_puntos():
    x = np.array([0.5, 1, 2, 3, 5, 8])
    curva = analisis.ajustar_curva(x, np.full(6, 0.10))
    assert curva.tipo == "ns" and float(curva.tir(4.0)) == pytest.approx(0.10, abs=1e-9)
    log = analisis.ajustar_curva(np.array([1.0, 2.0, 4.0]), np.array([0.05, 0.06, 0.07]))
    assert log.tipo == "log" and log.tir(2.0) == pytest.approx(0.06, abs=1e-9)
    assert analisis.ajustar_curva(np.array([1.0, 2.0]), np.array([0.05, 0.06])) is None


def test_spread_vs_curva_marca_barato_y_caro():
    df = _tabla(tir=[0.08, 0.09, 0.115, 0.11, 0.12, 0.05, 0.05, 0.05, 0.30])  # A3 rinde de más
    out = analisis.agregar_valor_relativo(df, analisis.curvas_por_familia(df), {"rico_barato_pb": 30})
    fila = out.set_index("ticker")
    assert fila.loc["A3", "spread_vs_curva_pb"] > 0
    assert set(out["senal_rv"].dropna()) <= {"barato", "caro", "en_curva"}
    assert pd.isna(fila.loc["F1", "spread_vs_curva_pb"])  # familia de un solo punto: sin curva


def test_spread_de_legislacion():
    df = pd.DataFrame({"ticker": ["GD30", "AL30"], "par": ["AL30", "GD30"], "ley": ["NY", "local"],
                       "tir": [0.07, 0.085]})
    out = analisis.agregar_spread_ley(df).set_index("ticker")
    assert out.loc["AL30", "spread_ley_pb"] == pytest.approx(150.0) == out.loc["GD30", "spread_ley_pb"]


def test_breakeven_lecap_vs_cer():
    df = _tabla()
    curva_cer = analisis.ajustar_curva(np.array([0.5, 1.0, 2.0]), np.array([0.05, 0.05, 0.05]))
    out = analisis.agregar_breakeven(df, curva_cer).set_index("ticker")
    assert out.loc["F1", "breakeven_anual"] == pytest.approx(1.30 / 1.05 - 1, abs=1e-9)
    assert out.loc["F1", "breakeven_mensual"] == pytest.approx((1.30 / 1.05) ** (1 / 12) - 1, abs=1e-9)
    assert pd.isna(out.loc["A1", "breakeven_anual"])
    assert analisis.agregar_breakeven(df, None)["breakeven_anual"].isna().all()


def test_score_entre_0_y_100_y_premia_liquidez_y_rendimiento():
    out = analisis.analizar(_tabla(), {"dias_min_curva": 20})
    assert out["score_rf_bruto"].between(0, 100).all()
    fila = out.set_index("ticker")
    # A2 (1e7) y A4 (1e5) operan menos que el mínimo para comprar: score_rf vacío, el bruto se conserva
    assert not fila.loc["A4", "apto_compra"] and "poco volumen" in fila.loc["A4", "motivo_no_apto"]
    assert pd.isna(fila.loc["A2", "score_rf"]) and fila.loc["A5", "apto_compra"]
    assert fila.loc["A5", "score_rendimiento"] > fila.loc["A1", "score_rendimiento"]
    assert fila.loc["A4", "score_liquidez"] == 0.0 and fila.loc["F1", "score_liquidez"] == 100.0


def test_score_ignora_rendimiento_de_lo_que_vence_ya():
    df = _tabla(dias=[400, 800, 1200, 1600, 5, 200, 400, 800, 200])
    out = analisis.agregar_score(analisis.agregar_valor_relativo(df, {}), {"dias_min_curva": 20})
    assert out.set_index("ticker").loc["A5", "score_rendimiento"] == 0.0


def test_resumen_curvas():
    out = analisis.analizar(_tabla())
    res = analisis.resumen_curvas(out)
    assert set(res) == {"soberano_usd", "cer", "lecap"}
    assert res["soberano_usd"]["n"] == 5 and res["soberano_usd"]["tir_media"] == pytest.approx(0.10)
    assert len(res["soberano_usd"]["curvas"]["global"]) == analisis.PUNTOS_CURVA
    assert res["lecap"]["curvas"] == {}


# ----------------------------------------------------------------------------- integración sin red

def test_cargar_renta_fija_offline(monkeypatch, cotiz):
    letras = parsers.parsear_letras_argentinadatos(fixture("rf_ad_letras.json"))
    monkeypatch.setattr(datos, "cotizaciones", lambda *a, **k: cotiz)
    monkeypatch.setattr(datos, "letras", lambda *a, **k: letras)
    monkeypatch.setattr(datos, "serie_cer", lambda *a, **k: parsers.parsear_cer_bcra(fixture("rf_bcra_cer.json")))
    monkeypatch.setattr(datos, "feriados", lambda *a, **k: parsers.parsear_feriados(fixture("rf_feriados_2026.json")))
    df = servicio.cargar_renta_fija(date(2026, 10, 11), inflacion_mensual=0.02)
    assert df["liquidacion"].iloc[0] == date(2026, 10, 13)
    assert {"soberano_usd", "lecap", "boncap", "cer", "on_usd"} <= set(df["clase"])
    columnas = {"ticker", "clase", "precio", "precio_ars", "moneda", "tir", "tem", "duration", "vencimiento",
                "paridad", "volumen_ars", "spread_vs_curva_pb", "score_rf", "carry_real", "ticker_iol"}
    assert columnas <= set(df.columns)
    assert df["precio"].notna().all() and df["tir"].notna().all()
    assert set(analisis.resumen_curvas(df)) == set(df["clase"])


def test_cache_de_fecha_pasada_sin_snapshot_falla(monkeypatch, tmp_path):
    monkeypatch.setattr(datos, "CACHE_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        datos._cacheado("x", date(2020, 1, 1), lambda: {"no": "debería llamarse"})
    (tmp_path / "rf_y_20200101.json").write_text('{"ok": 1}', encoding="utf-8")
    assert datos._cacheado("y", date(2020, 1, 1), lambda: None) == {"ok": 1}


# ----------------------------------------------------------------------------- filtro de calidad (auditoría)
from src.renta_fija import calidad  # noqa: E402


def _tabla_calidad(**extra) -> pd.DataFrame:
    base = _tabla()
    n = len(base)
    cols = {"vol_nominal_ars": [1e6] * n, "vol_nominal_tir": [1e6] * n, "spread_puntas_ars": [0.002] * n,
            "confianza": ["alta"] * n}
    return base.assign(**{**cols, **extra})


def test_tir_absurda_no_puede_dar_score_alto_ni_comprarse():
    # A5 con TIR 85% en USD (precio viejo/mal cargado): antes era el mejor score de su clase
    df = _tabla_calidad(tir=[0.08, 0.09, 0.10, 0.11, 0.85, 0.05, 0.05, 0.05, 0.30],
                        carry_usd=[0.006, 0.007, 0.008, 0.009, 0.06, 0.010, 0.010, 0.010, 0.011])
    out = analisis.analizar(df).set_index("ticker")
    assert not out.loc["A5", "apto_compra"] and "fuera de rango" in out.loc["A5", "motivo_no_apto"]
    assert pd.isna(out.loc["A5", "score_rf"])
    # y no ensucia la curva: se ajusta sin el outlier (duration máx. 4 = A4) y los demás quedan "en curva"
    assert analisis.curvas_por_familia(df)["global"].dur_max == 4.0
    assert set(out.loc[["A1", "A2", "A3", "A4"], "senal_rv"]) == {"en_curva"}


def test_precio_sin_operaciones_puntas_abiertas_y_confianza_baja_no_se_compran():
    df = _tabla_calidad(vol_nominal_ars=[0.0, 1e6, 1e6, 1e6, 1e6, 1e6, 1e6, 1e6, 1e6],
                        vol_nominal_tir=[1e6, 1e6, 1e6, 1e6, 1e6, 0.0, 1e6, 1e6, 1e6],
                        spread_puntas_ars=[0.002, 0.002, 0.10, 0.002, 0.002, 0.002, 0.002, 0.002, 0.002],
                        confianza=["alta"] * 6 + ["baja", "alta", "alta"])
    out = analisis.analizar(df).set_index("ticker")
    assert "precio viejo" in out.loc["A1", "motivo_no_apto"]       # la especie en pesos no operó
    assert "precio viejo" in out.loc["C1", "motivo_no_apto"]       # la especie de la TIR no operó
    assert "puntas" in out.loc["A3", "motivo_no_apto"]
    assert "confianza baja" in out.loc["C2", "motivo_no_apto"]
    assert out.loc[["A1", "A3", "C1", "C2"], "score_rf"].isna().all()
    assert out.loc["A5", "apto_compra"] and out.loc["A5", "score_rf"] == out.loc["A5", "score_rf_bruto"]


def test_vence_pronto_o_lejos_de_curva_no_se_compra():
    df = _tabla_calidad(dias=[400, 800, 1200, 1600, 10, 200, 400, 800, 200])
    out = analisis.analizar(df).set_index("ticker")
    assert "vence muy pronto" in out.loc["A5", "motivo_no_apto"]
    lejos = calidad.marcar_aptos(df.assign(spread_vs_curva_pb=[0, 0, 900, 0, 0, 0, 0, 0, 0]))
    assert "lejos de su curva" in lejos.set_index("ticker").loc["A3", "motivo_no_apto"]


def test_calidad_parametros_desde_yaml(cfg):
    p = calidad.parametros(cfg["parametros"])
    assert p["tir_rango"]["usd"] == [-0.05, 0.30] and "baja" in p["confianza_excluida"]
    assert calidad.marcar_aptos(pd.DataFrame())["apto_compra"].empty


def test_evaluar_informa_volumen_y_puntas_para_el_filtro(cfg, cotiz):
    ctx = valuacion.Contexto(date(2026, 10, 13), None, valuacion.mep_implicito(cotiz), 0.02, 0.01)
    al30 = valuacion.evaluar("AL30", cfg["instrumentos"]["AL30"], cotiz, ctx)
    assert al30["vol_nominal_ars"] == cotiz.loc["AL30", "volumen_nominal"]
    assert al30["vol_nominal_tir"] == cotiz.loc["AL30D", "volumen_nominal"]   # la TIR sale de la especie D
    assert 0 < al30["spread_puntas_ars"] < 0.01


def test_cache_del_dia_se_renueva_con_ttl_y_cae_al_viejo_si_falla(monkeypatch, tmp_path):
    import os as _os
    import requests as _rq
    monkeypatch.setattr(datos, "CACHE_DIR", tmp_path)
    hoy = date.today()
    assert datos._cacheado("q", hoy, lambda: {"v": 1}, ttl_min=20) == {"v": 1}
    assert datos._cacheado("q", hoy, lambda: {"v": 2}, ttl_min=20) == {"v": 1}      # fresco: no baja
    ruta = datos._ruta_cache("q", hoy)
    viejo = ruta.stat().st_mtime - 3600
    _os.utime(ruta, (viejo, viejo))
    assert datos._cacheado("q", hoy, lambda: {"v": 3}, ttl_min=20) == {"v": 3}      # vencido: renueva
    _os.utime(ruta, (viejo, viejo))

    def falla():
        raise _rq.ConnectionError("sin red")
    assert datos._cacheado("q", hoy, falla, ttl_min=20) == {"v": 3}                  # falla: usa el viejo
    with pytest.raises(_rq.ConnectionError):
        datos._cacheado("nuevo", hoy, falla, ttl_min=20)


def test_cerca_del_pago_de_cupon_no_se_compra():
    df = _tabla_calidad(dias_proximo_pago=[3, 30, 30, 30, 2000, 30, 30, 30, 200])
    out = calidad.marcar_aptos(df).set_index("ticker")
    assert "corte de cupón" in out.loc["A1", "motivo_no_apto"]
    assert out.loc["A5", "apto_compra"]  # bullet: el único pago es el vencimiento
