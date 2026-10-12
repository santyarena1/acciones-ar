"""Tests del parser del reporte semanal de Gorostiaga Bursátil (sin red)."""
import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.data import gorostiaga as g
from src.data.gorostiaga import parse_reporte
from src.data.gorostiaga_parse import etiquetar_eventos, num_ar

FIXTURE = Path(__file__).parent / "fixtures" / "gorostiaga_S212.txt"

UNIVERSE = [
    {"ticker": "PAMP", "adr": "PAM"}, {"ticker": "YPFD", "adr": "YPF"}, {"ticker": "CEPU", "adr": "CEPU"},
    {"ticker": "ALUA", "adr": None}, {"ticker": "TECO2", "adr": "TEO"}, {"ticker": "TXAR", "adr": None},
    {"ticker": "VIST"}, {"ticker": "MELI"},
]

RESUMEN_214 = """Resumen — Reporte Semanal de Mercados n°214
Lunes 05 de octubre de 2026
LO MÁS DESTACADO DE LA SEMANA
La Argentina siguió testeando nuevos mínimos.
RIESGO PAÍS DÓLAR CCL DÓLAR MAYORISTA
650 pb $1.625 $1.525,50
ACTIVO BANCO RECOMENDACIÓN DETALLE
Petrobras (PBR) JP Morgan Sobreponderar Precio objetivo de USD 24 por ADR. Destaca su generación de
caja.
Aluar (ALUA) Allaria Mantener Sus múltiplos actuales no ofrecen descuento.
EMPRESA (TICKER) SEMANA 2026 RESUMEN
Pampa Energía (PAM) -2,2% -14,0% Sin novedades puntuales en el reporte.
MercadoLibre (MELI) -3,9% -16,3% Goldman Sachs (Comprar, PO USD 2.300) y Morgan Stanley (Sobreponderar, PO USD
2.450) reiteraron su visión positiva.
Corp. América Airports +1,7% -6,6% Favorecida por la renegociación de su concesión hasta 2049, con un plan de
(CAAP) inversión de USD 600 M.
EL MUNDO: un dato de empleo flojo
"""


# El texto real del reporte es de Gorostiaga Bursátil: no se publica en el repositorio. Sin el archivo local,
# los tests que lo usan se saltean (el resto corre igual).
requiere_fixture = pytest.mark.skipif(not FIXTURE.exists(), reason="falta el texto local del reporte S212")


@pytest.fixture(scope="module")
def rep212() -> dict:
    if not FIXTURE.exists():
        pytest.skip("falta el texto local del reporte S212")
    return parse_reporte(FIXTURE.read_text(encoding="utf-8").split("\f"))


def _adr(rep: dict, ticker: str) -> dict:
    return next(a for a in rep["adrs"] if a["ticker"] == ticker)


def _noticia(rep: dict, ticker: str) -> dict:
    return next(n for n in rep["noticias"] if n["ticker"] == ticker)


# ---------------------------------------------------------------- parseo S212 (formato completo)
def test_encabezado(rep212):
    assert rep212["numero"] == 212
    assert rep212["fecha"] == "2026-09-21"
    assert rep212["formato"] == "completo"
    assert rep212["resumen"].startswith("La Fed confirmó")


def test_macro(rep212):
    assert rep212["riesgo_pais"] == 525
    assert rep212["ccl"] == 1600.0
    assert rep212["brecha_pct"] == 5.8


def test_tabla_adrs(rep212):
    assert len(rep212["adrs"]) == 21
    tx = _adr(rep212, "TX")
    assert tx == {"empresa": "Ternium", "ticker": "TX", "precio_usd": 56.67, "mcap_usd_m": 11403.5,
                  "var_semana": 0.3, "var_mes": 6.0, "var_anio": 52.1}
    pam = _adr(rep212, "PAM")
    assert (pam["var_semana"], pam["var_mes"], pam["var_anio"]) == (-3.5, 1.5, -5.6)
    meli = _adr(rep212, "MELI")
    assert meli["precio_usd"] == 1792.02 and meli["mcap_usd_m"] == 92532.3
    assert _adr(rep212, "TGS")["empresa"] == "Transportadora de Gas del Sur"


def test_recomendaciones_respectivamente(rep212):
    recs = {r["ticker"]: r for r in rep212["recomendaciones"] if r["fuente"] == "JP Morgan"}
    assert recs["VIST"]["rating"] == "Sobreponderar" and recs["VIST"]["precio_objetivo_usd"] == 94
    assert recs["YPF"]["rating"] == "Sobreponderar" and recs["YPF"]["precio_objetivo_usd"] == 66
    assert recs["VIST"]["horizonte"] == "diciembre de 2027"
    assert recs["PAM"]["rating"] == "Neutral" and recs["PAM"]["precio_objetivo_usd"] == 105


def test_noticias_y_eventos(rep212):
    assert "dividendo" in _noticia(rep212, "CEPU")["eventos"]
    assert "desinversion" in _noticia(rep212, "CEPU")["eventos"]
    alua = _noticia(rep212, "ALUA")
    assert alua["empresa"] == "ALUAR" and "resultado_positivo" in alua["eventos"]
    assert "rigi" in _noticia(rep212, "TGNO4")["eventos"]
    assert "litigio" in _noticia(rep212, "BIOX")["eventos"]
    # el párrafo de JP Morgan no se pega a la noticia de YPF
    assert "JP Morgan" not in _noticia(rep212, "YPF")["texto"]


def test_noticia_sin_ticker():
    paginas = ["Reporte Semanal de Mercados n°212\nLunes 21 de septiembre de 2026\nARGENTINA: Renta Variable\n"
               "Fin del párrafo anterior.\nRIZOBACTER sufrió un marcado deterioro al cerrar con una\n"
               "pérdida neta de ARS 36.798 M."]
    n = parse_reporte(paginas)["noticias"]
    assert n == [{"ticker": None, "empresa": "RIZOBACTER", "texto": n[0]["texto"],
                  "eventos": ["resultado_negativo"]}]


# ---------------------------------------------------------------- formato resumen (n°214)
def test_formato_resumen():
    rep = parse_reporte(RESUMEN_214.split("\f"))
    assert rep["formato"] == "resumen" and rep["numero"] == 214 and rep["fecha"] == "2026-10-05"
    assert rep["riesgo_pais"] == 650 and rep["ccl"] == 1625.0 and rep["brecha_pct"] is None
    caap = _adr(rep, "CAAP")  # el ticker venía en la línea siguiente
    assert caap["var_semana"] == 1.7 and caap["var_anio"] == -6.6
    recs = {(r["fuente"], r["ticker"]): r for r in rep["recomendaciones"]}
    assert recs[("JP Morgan", "PBR")]["precio_objetivo_usd"] == 24
    assert recs[("Allaria", "ALUA")]["rating"] == "Mantener"
    assert recs[("Morgan Stanley", "MELI")]["precio_objetivo_usd"] == 2450
    assert {n["ticker"] for n in rep["noticias"]} == {"MELI", "CAAP"}


# ---------------------------------------------------------------- robustez y utilidades
@pytest.mark.parametrize("entrada", [[], [""], ["basura sin formato"], None, [None, 123]])
def test_parse_no_explota(entrada):
    rep = parse_reporte(entrada)
    assert rep["numero"] is None and rep["adrs"] == [] and rep["avisos"]


def test_num_ar():
    assert num_ar("11.403,5") == 11403.5
    assert num_ar("-3,5") == -3.5
    assert num_ar("+0,3%") == 0.3
    assert num_ar("1.600") == 1600.0
    assert num_ar("x") is None and num_ar(None) is None


def test_etiquetas():
    assert etiquetar_eventos("Aprobó un programa de recompra de acciones") == ["recompra"]
    assert etiquetar_eventos("Colocó obligaciones negociables") == ["emision_deuda"]
    assert etiquetar_eventos("Moody's elevó su calificación") == ["calificacion"]


def test_numero_esperado():
    assert g.numero_esperado(date(2026, 9, 21)) == 212
    assert g.numero_esperado(date(2026, 9, 27)) == 212
    assert g.numero_esperado(date(2026, 9, 28)) == 213
    assert g.numero_esperado(date(2026, 10, 11)) == 214
    assert g.fecha_de_numero(214) == date(2026, 10, 5)


# ---------------------------------------------------------------- contexto
def test_contexto_por_ticker(rep212):
    ctx = g.contexto_por_ticker([rep212], UNIVERSE)
    pamp = ctx["PAMP"]
    assert pamp["recomendaciones"][0]["fuente"] == "JP Morgan"
    assert pamp["upside_consenso"] == pytest.approx(105 / 82.02 - 1, abs=1e-4)
    assert pamp["var_semana_adr"] == -3.5
    assert ctx["YPFD"]["upside_consenso"] == pytest.approx(66 / 54.52 - 1, abs=1e-4)
    assert ctx["VIST"]["upside_consenso"] == pytest.approx(94 / 72.26 - 1, abs=1e-4)
    assert "dividendo" in ctx["CEPU"]["eventos"] and ctx["CEPU"]["noticias"][0]["numero"] == 212
    assert "resultado_positivo" in ctx["ALUA"]["eventos"]
    assert ctx["CEPU"]["upside_consenso"] is None
    assert "TGNO4" not in ctx  # fuera del universo


def test_contexto_ordena_y_filtra_semanas():
    viejo = {"numero": 200, "fecha": "2026-06-29", "adrs": [], "recomendaciones": [],
             "noticias": [{"ticker": "CEPU", "texto": "viejo", "eventos": ["dividendo"]}]}
    r1 = {"numero": 213, "fecha": "2026-09-28", "adrs": [], "recomendaciones": [],
          "noticias": [{"ticker": "CEPU", "texto": "a", "eventos": ["rigi"]}]}
    r2 = {"numero": 214, "fecha": "2026-10-05", "adrs": [], "recomendaciones": [],
          "noticias": [{"ticker": "CEPU", "texto": "b", "eventos": ["adquisicion"]}]}
    ctx = g.contexto_por_ticker([r1, viejo, r2], UNIVERSE, semanas=4)
    assert [n["texto"] for n in ctx["CEPU"]["noticias"]] == ["b", "a"]
    assert ctx["CEPU"]["eventos"] == ["adquisicion", "rigi"]


def test_macro_ultimo_completa_con_anterior():
    reps = [{"numero": 213, "fecha": "2026-09-28", "resumen": "x", "riesgo_pais": 609, "ccl": 1599.0,
             "brecha_pct": 6.3},
            {"numero": 214, "fecha": "2026-10-05", "resumen": "y", "riesgo_pais": 650, "ccl": 1625.0,
             "brecha_pct": None}]
    m = g.macro_ultimo(reps)
    assert (m["numero"], m["riesgo_pais"], m["ccl"], m["brecha_pct"]) == (214, 650, 1625.0, 6.3)
    assert g.macro_ultimo([])["numero"] is None


# ---------------------------------------------------------------- I/O con red mockeada
def _resp(status: int, content: bytes) -> MagicMock:
    r = MagicMock()
    r.status_code, r.content = status, content
    return r


def test_descargar(tmp_path):
    s = MagicMock()
    s.get.return_value = _resp(200, b"%PDF-1.7 ...")
    p = g.descargar(215, tmp_path, session=s)
    assert p == tmp_path / "S215.pdf" and p.read_bytes().startswith(b"%PDF")
    assert "User-Agent" in s.get.call_args.kwargs["headers"] and s.get.call_args.kwargs["timeout"]
    s.get.return_value = _resp(404, b"<!DOCTYPE html>")
    assert g.descargar(216, tmp_path, session=s) is None
    s.get.return_value = _resp(200, b"<!DOCTYPE html>")
    assert g.descargar(217, tmp_path, session=s) is None and not (tmp_path / "S217.pdf").exists()


@requiere_fixture
def test_actualizar_no_redescarga(tmp_path, monkeypatch):
    (tmp_path / "S213.json").write_text(json.dumps({"numero": 213}), encoding="utf-8")
    (tmp_path / "S214.pdf").write_bytes(b"%PDF-")  # PDF ya bajado, sin JSON
    monkeypatch.setattr(g, "extraer_paginas", lambda pdf: FIXTURE.read_text(encoding="utf-8").split("\f"))
    s = MagicMock()
    s.get.return_value = _resp(404, b"")
    nuevos = g.actualizar(tmp_path, hoy=date(2026, 10, 11), session=s)
    pedidos = sorted(c.args[0] for c in s.get.call_args_list)
    assert pedidos == [g.URL.format(n=n) for n in (211, 212, 215)]  # ni 213 ni 214
    assert len(nuevos) == 1 and (tmp_path / "S214.json").exists()
    assert not list(tmp_path.glob("*.pdf"))                         # el PDF nunca queda guardado
    hist = g.cargar_historial(tmp_path)
    assert [r["numero"] for r in hist] == [212, 213]  # el S214.json tiene el texto de la 212
