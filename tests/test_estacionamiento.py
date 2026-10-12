import pandas as pd

from src.portfolio.renta_fija_alloc import elegir_estacionamiento, objetivo_estacionamiento

RF = pd.DataFrame({
    "clase": ["lecap", "lecap", "lecap", "boncap", "cer"],
    "dias": [5, 31, 48, 230, 60],
    "tem": [0.017, 0.0189, 0.0190, 0.0219, 0.03],
    "apto_compra": [False, True, True, True, True],
    "volumen_ars": [3e10, 2.7e10, 3.2e10, 1.3e10, 5e10],
}, index=["S16O6", "S13N6", "S30N6", "T31Y7", "TZX27"])


def test_elige_lecap_corta_liquida_de_mayor_tasa():
    assert elegir_estacionamiento(RF) == "S30N6"          # ni la que vence ya, ni la larga, ni la CER


def test_estaciona_solo_lo_que_sobra(settings):
    t = objetivo_estacionamiento({"SPY": 0.5, "GGAL": 0.3}, RF, 1_000_000, settings)
    assert t == {"S30N6": round(1 - 0.8 - settings["caja"]["operativa"], 4)}


def test_no_estaciona_montos_chicos_ni_sin_candidata(settings):
    assert objetivo_estacionamiento({"SPY": 0.95}, RF, 1_000_000, settings) == {}       # sobra 3%: < posición mínima
    assert objetivo_estacionamiento({"SPY": 0.5}, RF.iloc[0:0], 1_000_000, settings) == {}
