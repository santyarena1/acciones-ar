"""Reportes semanales: los PDFs nunca se guardan; persiste todo lo extraído y no se vuelve a bajar lo guardado."""
import json
from datetime import date

from src import db
from src.data import gorostiaga as g

HOY = date(2026, 10, 12)
ESPERADO = g.numero_esperado(HOY)
TEXTO = "Reporte Semanal\nAL30 09/07/2030 0,75% 61.500,00 12,50%\n"


def _bajador(numeros_ok, vistos, pdfs):
    def bajar(n, destino, session=None):
        vistos.append(n)
        if n not in numeros_ok:
            return None
        destino.mkdir(parents=True, exist_ok=True)
        pdf = destino / f"S{n}.pdf"
        pdf.write_bytes(b"%PDF-1.7")
        pdfs.append(pdf)
        return pdf
    return bajar


def test_archivos_pdf_se_borra_y_queda_todo_en_el_json(tmp_path, monkeypatch):
    vistos, pdfs = [], []
    monkeypatch.setattr(g, "descargar", _bajador({ESPERADO}, vistos, pdfs))
    monkeypatch.setattr(g, "extraer_paginas", lambda pdf: [TEXTO])
    nuevos = g.actualizar(tmp_path, hoy=HOY)
    assert [r["numero"] for r in nuevos] == [ESPERADO]
    assert not list(tmp_path.glob("*.pdf")) and not pdfs[0].exists()
    rep = json.loads((tmp_path / f"S{ESPERADO}.json").read_text(encoding="utf-8"))
    for campo in ("numero", "fecha", "formato", "resumen", "url", "riesgo_pais", "ccl", "brecha_pct", "adrs",
                  "recomendaciones", "noticias", "avisos", "tablas_bonos"):
        assert campo in rep, campo
    assert rep["tablas_bonos"][0]["ticker"] == "AL30" and rep["tablas_bonos"][0]["vencimiento"] == "2030-07-09"
    vistos.clear()
    assert g.actualizar(tmp_path, hoy=HOY) == [] and ESPERADO not in vistos      # no se vuelve a bajar


def test_archivos_pdf_se_borra_aunque_falle_el_parseo(tmp_path, monkeypatch):
    vistos, pdfs = [], []
    monkeypatch.setattr(g, "descargar", _bajador({ESPERADO}, vistos, pdfs))

    def roto(pdf):
        raise RuntimeError("pdf corrupto")
    monkeypatch.setattr(g, "extraer_paginas", roto)
    g.actualizar(tmp_path, hoy=HOY)
    assert not pdfs[0].exists()
    rep = json.loads((tmp_path / f"S{ESPERADO}.json").read_text(encoding="utf-8"))
    assert rep["numero"] == ESPERADO and any("parseo" in a for a in rep["avisos"])
    vistos.clear()
    g.actualizar(tmp_path, hoy=HOY)
    assert ESPERADO not in vistos                                                 # el registro alcanza


def test_archivos_borra_pdfs_viejos_que_ya_tienen_json(tmp_path, monkeypatch):
    (tmp_path / "S100.pdf").write_bytes(b"%PDF")
    (tmp_path / "S100.json").write_text(json.dumps({"numero": 100}), encoding="utf-8")
    monkeypatch.setattr(g, "descargar", lambda *a, **k: None)
    g.actualizar(tmp_path, hoy=HOY)
    assert not (tmp_path / "S100.pdf").exists() and (tmp_path / "S100.json").exists()


def test_db_pdf_temporal_y_registro_completo(base_sqlite, monkeypatch):
    vistos, pdfs = [], []
    monkeypatch.setattr(g, "descargar", _bajador({ESPERADO, ESPERADO - 1}, vistos, pdfs))
    paginas = {ESPERADO: [TEXTO]}
    monkeypatch.setattr(g, "extraer_paginas", lambda pdf: paginas.get(int(pdf.stem[1:]), []))
    g.actualizar(hoy=HOY)
    assert len(pdfs) == 2 and not any(p.exists() for p in pdfs)
    guardados = {r["numero"]: r for r in db.cargar_reportes()}
    assert set(guardados) == {ESPERADO, ESPERADO - 1}
    assert guardados[ESPERADO]["tablas_bonos"][0]["ticker"] == "AL30"
    assert "pdf: no se pudo leer el texto" in guardados[ESPERADO - 1]["avisos"]
    vistos.clear()
    assert g.actualizar(hoy=HOY) == [] and not {ESPERADO, ESPERADO - 1} & set(vistos)
