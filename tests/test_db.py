"""Capa de base de datos (SQLite en los tests, Postgres en la nube) y backends que cambian con DATABASE_URL."""
import re
from datetime import date, timedelta

import pandas as pd
import pytest

from src import config, db, store
from src.broker.paper import AlmacenArchivo, AlmacenDB, PaperBroker
from src.data import gorostiaga as g
from src.operador import bitacora as bmod
from src.operador.bitacora import Bitacora, OperadorOcupado, abrir_bitacora
from src.operador.bitacora_db import BitacoraDB


# ----------------------------------------------------------------------------- conexión y esquema
def test_normalizar_url_fuerza_psycopg():
    assert db.normalizar_url("postgres://u:p@h/db?sslmode=require") == "postgresql+psycopg://u:p@h/db?sslmode=require"
    assert db.normalizar_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert db.normalizar_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert db.normalizar_url("sqlite:///x.db") == "sqlite:///x.db"


def test_sin_database_url_no_hay_db():
    assert db.hay_db() is False
    with pytest.raises(RuntimeError):
        db.motor()


def _columnas_schema_sql() -> dict[str, list[str]]:
    sql = db.SCHEMA_SQL.read_text(encoding="utf-8")
    tablas = {}
    for s in db.sentencias_schema(sql):
        m = re.match(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*)\)$", s, re.S)
        if m:
            tablas[m.group(1)] = [ln.strip().split()[0] for ln in re.split(r",\s*\n", m.group(2)) if ln.strip()]
    return tablas


def test_metadata_portable_coincide_con_schema_sql():
    sql = _columnas_schema_sql()
    assert set(sql) == set(db.metadata.tables)
    for nombre, cols in sql.items():
        assert cols == [c.name for c in db.metadata.tables[nombre].columns], nombre


def test_sentencias_schema_sin_comentarios():
    partes = db.sentencias_schema("-- hola; chau\nCREATE TABLE a (x int); -- fin\nCREATE INDEX i ON a (x);")
    assert partes == ["CREATE TABLE a (x int)", "CREATE INDEX i ON a (x)"]


def test_aplicar_esquema_en_sqlite_es_idempotente(base_sqlite):
    assert db.aplicar_esquema() == len(db.metadata.tables)
    assert db.aplicar_esquema() == len(db.metadata.tables)


# ----------------------------------------------------------------------------- kv, eventos, reportes, comandos
def test_kv_upsert_y_lectura(base_sqlite):
    assert db.kv_get("estado", "x", {"defecto": 1}) == {"defecto": 1}
    db.kv_set("estado", "x", {"a": 1, "lista": [1, "dos"]})
    db.kv_set("estado", "x", {"a": 2})
    db.kv_set_varios("estado", {"y": "texto", "z": None})
    assert db.kv_get("estado", "x") == {"a": 2}
    assert db.kv_todos("estado") == {"x": {"a": 2}, "y": "texto", "z": None}
    db.kv_borrar("estado", "x")
    assert "x" not in db.kv_todos("estado")


def test_eventos_filtros_y_orden(base_sqlite):
    t0 = db.ahora_utc()
    for i, tipo in enumerate(["a", "b", "a"]):
        db.insertar_evento(tipo, "paper" if i else None, {"i": i}, t0 + timedelta(seconds=i))
    assert [e["datos"]["i"] for e in db.consultar_eventos()] == [0, 1, 2]
    assert [e["datos"]["i"] for e in db.consultar_eventos(tipos=["a"])] == [0, 2]
    assert [e["datos"]["i"] for e in db.consultar_eventos(ultimos=2)] == [1, 2]
    assert [e["datos"]["i"] for e in db.consultar_eventos(desde=t0 + timedelta(seconds=1))] == [1, 2]
    assert db.consultar_eventos()[0]["ts"].tzinfo is not None


def test_reportes_en_db(base_sqlite):
    db.guardar_reporte(214, date(2026, 10, 5), {"numero": 214, "ccl": 1500.0})
    db.guardar_reporte(213, None, {"numero": 213})
    assert db.numeros_reportes() == {213, 214}
    assert [r["numero"] for r in db.cargar_reportes()] == [213, 214]


def test_comandos_se_reclaman_una_sola_vez(base_sqlite):
    i = db.encolar_comando("revisar")
    assert [c["id"] for c in db.comandos_pendientes()] == [i]
    assert db.reclamar_comando(i) is True
    assert db.reclamar_comando(i) is False
    assert db.comandos_pendientes() == []
    db.resultado_comando(i, {"ok": True})
    fila = db.leer_comando(i)
    assert fila["resultado"] == {"ok": True} and fila["procesado"] is not None


# ----------------------------------------------------------------------------- bitácora en la base
def test_abrir_bitacora_elige_backend(tmp_path, base_sqlite, monkeypatch):
    assert isinstance(abrir_bitacora(), BitacoraDB)
    monkeypatch.delenv("DATABASE_URL")
    assert type(abrir_bitacora()) is Bitacora


def test_bitacora_db_eventos_en_hora_argentina(base_sqlite):
    bit = BitacoraDB()
    ev = bit.registrar("orden", modo="paper", ticker="GGAL", lado="COMPRAR", estado="enviada", precio=float("nan"))
    leido = bit.eventos()[-1]
    assert ev["ts"].endswith("-03:00") and leido["ts"] == ev["ts"]
    assert leido["modo"] == "paper" and leido["ticker"] == "GGAL" and leido["precio"] is None
    assert db.consultar_eventos()[-1]["modo"] == "paper"
    assert bit.ordenes_del_dia(date.fromisoformat(ev["ts"][:10])) == {("GGAL", "COMPRAR")}


def test_bitacora_db_ordenes_del_dia_como_archivos(base_sqlite):
    bit = BitacoraDB()
    hoy = date.fromisoformat(bmod.ahora_iso()[:10])
    bit.registrar("orden", ticker="A", lado="COMPRAR", estado="enviada")
    bit.registrar("orden", ticker="B", lado="COMPRAR", estado="rechazada")
    bit.registrar_intento("C", "VENDER", cantidad=3)
    assert bit.ordenes_del_dia(hoy) == {("A", "COMPRAR"), ("C", "VENDER")}
    assert bit.ordenes_del_dia(hoy - timedelta(days=1)) == set()


def test_bitacora_db_estado_pausa_y_claves(base_sqlite):
    bit = BitacoraDB()
    assert bit.estado() == {"pausado": False, "ultimo_rebalanceo": None}
    bit.pausar("prueba")
    assert bit.estado()["pausado"] is True and bit.estado()["motivo_pausa"] == "prueba"
    assert db.kv_get("estado", "pausado") == {"pausado": True, "motivo": "prueba"}
    bit.guardar_estado(aportes={"paper": {"total": 1.0}}, ultimo_pedido_fondos=None)
    bit.reanudar()
    est = bit.estado()
    assert est["pausado"] is False and est["aportes"] == {"paper": {"total": 1.0}}
    assert est["ultimo_pedido_fondos"] is None


def test_bitacora_db_pausa_ilegible_falla_cerrado(base_sqlite):
    db.kv_set("estado", "pausado", "cualquier cosa")
    assert BitacoraDB().estado()["pausado"] is True


def test_candado_db_excluye_y_se_libera(base_sqlite):
    bit = BitacoraDB()
    with bit.candado():
        assert "candado" not in bit.estado()
        with pytest.raises(OperadorOcupado):
            with BitacoraDB().candado():
                pass
    assert db.kv_get("estado", "candado") is None
    with pytest.raises(ValueError):
        with bit.candado():
            raise ValueError("boom")
    assert db.kv_get("estado", "candado") is None


def test_candado_db_abandonado_se_reemplaza(base_sqlite):
    viejo = db.ahora_utc() - timedelta(seconds=2 * bmod.CANDADO_VENCE_SEG)
    with base_sqlite.begin() as conn:
        conn.execute(db.estado.insert().values(clave="candado", valor={"pid": 1}, actualizado=viejo))
    bit = BitacoraDB()
    with bit.candado():
        assert db.kv_get("estado", "candado")["pid"] != 1
    assert any(e["tipo"] == "aviso" for e in bit.eventos())


# ----------------------------------------------------------------------------- corridas, preferencias, paper
def _corrida() -> store.Corrida:
    ranking = pd.DataFrame({"tipo": ["accion", "cedear"], "score": [70.5, float("nan")], "alertas": ["", None]},
                           index=["GGAL", "SPY"])
    rf = pd.DataFrame({"ticker": ["AL30"], "clase": ["soberano_usd"], "mult": [0.01]},
                      index=pd.Index(["AL30"], name="ticker_iol"))
    objetivos = pd.DataFrame({"clase": ["acciones_ar"], "peso_objetivo": [0.5], "peso_actual": [0.1]}, index=["GGAL"])
    ordenes = pd.DataFrame([{"ticker": "GGAL", "lado": "COMPRAR", "cantidad": 10, "precio_ref": 1000.0}])
    meta = {"broker": "paper", "fecha": pd.Timestamp("2026-10-12 12:00"), "cartera": {"valor_total": 1e6}}
    return store.Corrida("20261012_1200", meta, ranking, rf, objetivos, ordenes, "guía")


def test_corridas_en_db_ida_y_vuelta(base_sqlite):
    c = _corrida()
    assert store.guardar(c) is None and c.dir is None
    assert store.listar() == ["20261012_1200"]
    fila = db.cargar_corrida("20261012_1200")
    assert fila["modo"] == "paper" and fila["ranking"][0]["ticker"] == "GGAL"
    assert fila["renta_fija"][0]["ticker_iol"] == "AL30" and fila["objetivos"][0]["ticker"] == "GGAL"
    leida = store.ultima()
    assert list(leida.ranking.index) == ["GGAL", "SPY"] and leida.ranking.at["SPY", "alertas"] == ""
    assert pd.isna(leida.ranking.at["SPY", "score"]) and leida.renta_fija.index.name == "ticker_iol"
    assert leida.ordenes.iloc[0]["cantidad"] == 10 and leida.guia == "guía"
    assert leida.meta["fecha"].startswith("2026-10-12")


def test_corridas_con_base_explicita_siguen_en_archivos(tmp_path, base_sqlite):
    store.guardar(_corrida(), base=tmp_path)
    assert store.listar(tmp_path) == ["20261012_1200"] and store.listar() == []


def test_preferencias_en_db(base_sqlite, tmp_path):
    assert config.preferencias() == {}
    config.guardar_preferencias({"operador": {"perfil": "moderado"}})
    config.guardar_preferencias({"operador": {"modo": "paper"}})
    assert db.kv_get("preferencias", "usuario") == {"operador": {"perfil": "moderado", "modo": "paper"}}
    assert config.load_settings()["operador"]["perfil"] == "moderado"
    assert config.preferencias(tmp_path / "no_existe.yaml") == {}


def test_paper_en_db_persiste_y_reinicia(base_sqlite):
    b = PaperBroker(100_000, comision=0.0)
    assert isinstance(b.almacen, AlmacenDB)
    b.place_order("GGAL", "COMPRAR", 10, 1000.0)
    b2 = PaperBroker(0)
    assert b2.get_cash_ars() == 90_000 and b2.get_positions()["GGAL"]["cantidad"] == 10
    assert set(db.kv_get("paper", "cartera")) == {"caja", "posiciones", "historial"}
    b2.reiniciar(50_000)
    assert PaperBroker(0).get_cash_ars() == 50_000 and PaperBroker(0).get_positions() == {}
    assert isinstance(PaperBroker(0, path=base_sqlite.url.database + ".json").almacen, AlmacenArchivo)


def test_gorostiaga_en_db_no_rebaja_lo_guardado(base_sqlite, monkeypatch):
    hoy = date(2026, 10, 12)
    esperado = g.numero_esperado(hoy)
    db.guardar_reporte(esperado, None, {"numero": esperado})
    pedidos = []

    def bajar(n, destino, session=None):
        pedidos.append(n)
        if n != esperado - 1:
            return None
        pdf = destino / f"S{n}.pdf"
        pdf.write_bytes(b"%PDF")
        return pdf

    monkeypatch.setattr(g, "descargar", bajar)
    monkeypatch.setattr(g, "extraer_paginas", lambda pdf: ["Reporte\x00 vacío"])
    nuevos = g.actualizar(hoy=hoy)
    assert esperado not in pedidos and [r["numero"] for r in nuevos] == [esperado - 1]
    assert [r["numero"] for r in g.cargar_historial()] == [esperado - 1, esperado]
    pedidos.clear()
    assert g.actualizar(hoy=hoy) == [] and esperado - 1 not in pedidos
