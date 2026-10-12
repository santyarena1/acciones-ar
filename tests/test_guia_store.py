import pandas as pd

from src.config import load_universe
from src.guia import generar_guia, razones
from src.store import Corrida, cargar, guardar, listar, ultima


def _ranking():
    return pd.DataFrame({
        "tipo": ["cedear", "accion"], "sector": ["etf_indices", "bancos"], "score": [82.0, 30.0],
        "senal": ["COMPRAR", "REDUCIR / VENDER"], "tec_rel": [90.0, 10.0], "fund_rel": [None, 20.0],
        "sobre_sma200": [True, False], "upside_consenso": [None, 0.25], "rsi14": [60.0, 40.0],
        "en_cartera": [False, True], "alertas": ["", "REVISAR STOP: -30% desde el máximo"],
    }, index=["SPY", "GGAL"])


def test_razones_legibles():
    r = _ranking()
    assert any("momentum mejor que el 90%" in x for x in razones(r.loc["SPY"]))
    assert any("+25%" in x for x in razones(r.loc["GGAL"]))
    # numpy.bool_ también cuenta como tendencia alcista
    fila = r.loc["SPY"].copy()
    fila["sobre_sma200"] = pd.Series([True]).astype(bool).iloc[0]
    assert any("tendencia alcista" in x for x in razones(fila))


def test_guia_incluye_secciones():
    ordenes = pd.DataFrame([{"ticker": "GGAL", "lado": "VENDER", "cantidad": 10, "monto_ars": 60000, "nota": ""},
                            {"ticker": "SPY", "lado": "COMPRAR", "cantidad": 5, "monto_ars": 100000, "nota": ""}])
    g = generar_guia({"regimen": "adverso", "motivos": ["Riesgo país 1100 pb"]},
                     {"acciones_ar": 0.2, "cedears": 0.4, "caja": 0.4}, {"caja": 1.0}, "moderado",
                     _ranking(), ordenes, reporte={"numero": 214, "fecha": "2026-10-05", "resumen": "Semana dura."})
    assert "ADVERSO" in g and "**Vender 10 GGAL**" in g and "**Comprar 5 SPY**" in g
    assert "REVISAR STOP" in g and "n°214" in g and "no es asesoramiento" in g


def test_store_ida_y_vuelta(tmp_path):
    c = Corrida("20261011_1200", {"macro": {"score": float("nan")}, "perfil": "moderado"}, _ranking(),
                ordenes=pd.DataFrame([{"ticker": "SPY", "lado": "COMPRAR"}]), guia="# hola")
    guardar(c, tmp_path)
    assert listar(tmp_path) == ["20261011_1200"]
    c2 = cargar("20261011_1200", tmp_path)
    assert c2.meta["macro"]["score"] is None          # NaN -> null en JSON
    assert c2.ranking.loc["SPY", "alertas"] == ""     # texto vacío no vuelve como NaN
    assert ultima(tmp_path).guia == "# hola"


def test_universo_tiene_los_tres_grupos():
    u = load_universe()
    paneles = {a["panel"] for a in u}
    assert paneles == {"lider", "general", "cedears"}
    assert len({a["ticker"] for a in u}) == len(u)
    assert all(a["subyacente"] for a in u if a["tipo"] == "cedear")
    brk = next(a for a in u if a["ticker"] == "BRKB")
    assert brk["subyacente"] == "BRK-B"
