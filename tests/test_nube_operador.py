"""Operador en la nube: pedidos de la web, habilitación del modo real, revisión fuera de horario, resumen diario."""
from datetime import date, datetime

import pandas as pd
import pytest

from src import db
from src.broker.paper import PaperBroker
from src.operador import ejecutor as ej
from src.operador import resumen as rs
from src.operador.bitacora_db import BitacoraDB
from src.operador.comandos import procesar_comandos
from src.store import Corrida


@pytest.fixture
def avisos(monkeypatch):
    enviados = []

    def fake(titulo, texto):
        enviados.append((titulo, texto))
        return True
    monkeypatch.setattr(ej, "notificar", fake)
    monkeypatch.setattr(rs, "notificar", fake)
    return enviados


def _settings(settings, modo="paper"):
    return {**settings, "operador": {**settings["operador"], "modo": modo},
            "portfolio": {**settings["portfolio"], "paper_capital_inicial_ars": 1_000_000}}


# ----------------------------------------------------------------------------- comandos
def test_comandos_en_orden_y_marcados(base_sqlite, settings):
    s, bit = _settings(settings), BitacoraDB()
    ids = [db.encolar_comando("depositar_practica", {"monto": 250_000}),
           db.encolar_comando("depositar_practica", {"monto": -5}),
           db.encolar_comando("revisar"),
           db.encolar_comando("borrar_todo")]
    hechos = procesar_comandos(bit, s)
    assert [h["id"] for h in hechos] == ids
    assert [h["ok"] for h in hechos] == [True, False, True, False]
    assert PaperBroker(0).get_cash_ars() == 1_250_000
    assert db.comandos_pendientes() == [] and db.leer_comando(ids[1])["resultado"]["ok"] is False
    assert procesar_comandos(bit, s) == []                              # no se repiten
    assert [e["comando"] for e in bit.eventos(tipo="comando")] == ["depositar_practica"] * 2 + ["revisar", "borrar_todo"]


def test_reiniciar_practica_resetea_cartera_y_seguimiento(base_sqlite, settings):
    s, bit = _settings(settings), BitacoraDB()
    PaperBroker(1_000_000, comision=0.0).place_order("GGAL", "COMPRAR", 10, 1000.0)
    bit.guardar_estado(aportes={"paper": {"total": 1e6}, "live": {"total": 5.0}},
                       seguimiento={"paper": {"valor": 1e6}, "live": {"valor": 5.0}},
                       ultimo_pedido_fondos={"monto": 1, "texto": "x"})
    db.encolar_comando("reiniciar_practica", {"capital": 300_000})
    assert procesar_comandos(bit, s)[0]["ok"] is True
    p = PaperBroker(0)
    assert p.get_cash_ars() == 300_000 and p.get_positions() == {}
    est = bit.estado()
    assert est["aportes"] == {"live": {"total": 5.0}} and est["seguimiento"] == {"live": {"valor": 5.0}}
    assert est["ultimo_pedido_fondos"] is None


def test_sin_base_no_hay_comandos(tmp_path, settings):
    from src.operador.bitacora import Bitacora
    assert procesar_comandos(Bitacora(tmp_path), settings) == []


def test_operar_procesa_comandos_aunque_este_pausado(base_sqlite, settings, avisos):
    bit = BitacoraDB()
    bit.pausar("vacaciones")
    db.encolar_comando("depositar_practica", {"monto": 1000})
    r = ej.operar(_settings(settings), [], bitacora=bit)
    assert r.estado == "pausado" and db.comandos_pendientes() == []
    assert db.kv_get("estado", "candado") is None


# ----------------------------------------------------------------------------- modo real
def test_modo_real_exige_preferencia_y_habilitacion(settings, monkeypatch):
    live = _settings(settings, "live")
    assert "preferencias" in ej.motivo_sin_modo_real(_settings(settings), {"modo_real": {"habilitado": True}})
    assert "web" in ej.motivo_sin_modo_real(live, {})
    assert ej.motivo_sin_modo_real(live, {"modo_real": {"habilitado": "true"}}) is not None   # solo True exacto
    assert ej.motivo_sin_modo_real(live, {"modo_real": {"habilitado": True, "desde": "2026-10-12"}}) is None
    monkeypatch.setenv("IOL_LIVE_TRADING", "1")
    assert ej.motivo_sin_modo_real(live, {}) is None                     # alternativa local (.env)
    monkeypatch.setenv("IOL_LIVE_TRADING", "0")
    assert ej.motivo_sin_modo_real(live, {}) is not None


def test_operar_live_sin_habilitacion_no_crea_broker_real(base_sqlite, settings, avisos, monkeypatch):
    import src.servicio as servicio
    monkeypatch.setattr(ej, "mercado_abierto", lambda *a, **k: True)
    monkeypatch.setattr(ej, "feriados_ar", lambda: set())
    monkeypatch.setattr(servicio, "crear_broker", lambda *a, **k: pytest.fail("no debía crear broker"))
    r = ej.operar(_settings(settings, "live"), [], bitacora=BitacoraDB())
    assert r.estado == "error" and "ModoRealNoHabilitado" in r.mensaje


class BrokerRealFalso:
    nombre = "iol"

    def get_cash_ars(self):
        return 100_000.0

    def get_positions(self):
        return {}

    def open_orders(self):
        pytest.fail("fuera de horario no se tocan órdenes reales")

    def place_order(self, *a, **k):
        pytest.fail("fuera de horario no se mandan órdenes reales")

    cancel_order = get_quote = place_order


def _corrida_falsa(*a, **k):
    ordenes = pd.DataFrame([{"ticker": "GGAL", "lado": "COMPRAR", "cantidad": 10, "precio_ref": 1000.0}])
    meta = {"macro": {"regimen": "neutral"}, "cartera": {"valor_total": 100_000.0, "posiciones": {}, "caja": 1e5}}
    return Corrida("20261012_2000", meta, pd.DataFrame({"score": [80.0]}, index=["GGAL"]), ordenes=ordenes)


def test_revision_forzada_con_mercado_cerrado_en_real_solo_analiza(base_sqlite, settings, avisos, monkeypatch):
    import src.servicio as servicio
    bit = BitacoraDB()
    bit.guardar_estado(modo_real={"habilitado": True})
    monkeypatch.setattr(ej, "mercado_abierto", lambda *a, **k: False)
    monkeypatch.setattr(ej, "feriados_ar", lambda: set())
    monkeypatch.setattr(ej, "_precios_benchmark", lambda c: {})
    monkeypatch.setattr(servicio, "crear_broker", lambda *a, **k: BrokerRealFalso())
    monkeypatch.setattr(servicio, "correr", _corrida_falsa)
    r = ej.operar(_settings(settings, "live"), [], forzar_horario=True, bitacora=bit)
    assert r.estado == "analizado" and r.enviadas == []
    assert not bit.eventos(tipo="orden") and not bit.eventos(tipo="intento_orden")
    assert bit.eventos(tipo="salteo")[0]["motivo"].startswith("mercado cerrado")
    r2 = ej.operar(_settings(settings, "live"), [], forzar_horario=False, bitacora=bit)
    assert r2.estado == "cerrado"


def test_solo_analisis_con_mercado_abierto_en_real_no_manda_ordenes(base_sqlite, settings, avisos, monkeypatch):
    import src.servicio as servicio
    bit = BitacoraDB()
    bit.guardar_estado(modo_real={"habilitado": True})
    monkeypatch.setattr(ej, "mercado_abierto", lambda *a, **k: True)       # mercado ABIERTO
    monkeypatch.setattr(ej, "feriados_ar", lambda: set())
    monkeypatch.setattr(ej, "_precios_benchmark", lambda c: {})
    monkeypatch.setattr(servicio, "crear_broker", lambda *a, **k: BrokerRealFalso())
    monkeypatch.setattr(servicio, "correr", _corrida_falsa)                # el plan tiene una compra
    r = ej.operar(_settings(settings, "live"), [], solo_analisis=True, bitacora=bit)
    assert r.estado == "analizado" and r.enviadas == []
    assert not bit.eventos(tipo="orden") and not bit.eventos(tipo="intento_orden")
    assert bit.eventos(tipo="corrida")[-1]["solo_analisis"] is True


# ----------------------------------------------------------------------------- resumen diario
LUNES_1630 = datetime(2026, 10, 12, 16, 30)


def test_corresponde_resumen():
    assert rs.corresponde(LUNES_1630, set(), {})
    assert not rs.corresponde(LUNES_1630.replace(hour=15), set(), {})
    assert not rs.corresponde(LUNES_1630, {date(2026, 10, 12)}, {})                       # feriado
    assert not rs.corresponde(datetime(2026, 10, 11, 16, 30), set(), {})                  # domingo
    assert not rs.corresponde(LUNES_1630, set(), {"ultimo_resumen_diario": "2026-10-12"})


def test_texto_del_resumen():
    estado = {"seguimiento": {"paper": {"valor": 1_100_000, "indice": 1.05, "pico": 1.05, "bm_indice": 1.02}},
              "aportes": {"paper": {"total": 1_000_000}},
              "ultimo_pedido_fondos": {"texto": "Para ejecutar el plan completo faltan $50.000."}}
    ordenes = [{"modo": "paper", "lado": "COMPRAR", "cantidad": 10, "ticker": "GGAL", "precio": 5000, "estado": "x"},
               {"modo": "paper", "lado": "VENDER", "cantidad": 1, "ticker": "YPFD", "precio": 1, "estado": "rechazada"},
               {"modo": "live", "lado": "VENDER", "cantidad": 1, "ticker": "PAMP", "precio": 1, "estado": "x"}]
    t = rs.armar(estado, ordenes, "paper")
    assert "$1.100.000" in t and "$100.000 (+10,0%)" in t and "+5,0%" in t and "+2,0%" in t
    assert "Operaciones de hoy: 1" in t and "Compró 10 GGAL a $5.000" in t
    assert "YPFD" not in t and "PAMP" not in t and "faltan $50.000" in t


def test_resumen_una_sola_vez_por_dia(base_sqlite, avisos):
    bit = BitacoraDB()
    assert rs.enviar_si_corresponde(bit, "paper", LUNES_1630, set()) is True
    assert rs.enviar_si_corresponde(bit, "paper", LUNES_1630.replace(minute=50), set()) is False
    assert len(avisos) == 1 and avisos[0][0] == "Resumen del día"
    assert bit.estado()["ultimo_resumen_diario"] == "2026-10-12"
    assert bit.eventos(tipo="resumen_diario")[0]["enviado"] is True
    assert rs.enviar_si_corresponde(bit, "paper", datetime(2026, 10, 13, 16, 31), set()) is True
