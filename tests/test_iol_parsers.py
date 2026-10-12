"""Tests de los parsers de IOL y del cliente HTTP (sin red: sesión falsa, sleep parcheado)."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import requests

from src.broker.iol import (
    IOLBroker,
    IOLClient,
    IOLError,
    clasificar_tipo,
    multiplicador_precio,
    parse_cash_ars,
    parse_history,
    parse_operaciones,
    parse_order_response,
    parse_panel,
    parse_positions,
    parse_quote,
    validez_cierre_mercado,
)

FIX = Path(__file__).parent / "fixtures"
TOKEN = "tok-SECRETO-123"
PASSWORD = "clave-SUPER-secreta"


def fixture(nombre: str):
    return json.loads((FIX / nombre).read_text(encoding="utf-8"))


# --- parsers -------------------------------------------------------------
def test_parse_history():
    raw = [
        {"fechaHora": "2026-10-09T17:00:00", "ultimoPrecio": 1500.5, "volumenNominal": 1000},
        {"fechaHora": "2026-10-08T17:00:00", "ultimoPrecio": 1480.0, "volumenNominal": 900},
        {"fechaHora": "2026-10-07T17:00:00", "ultimoPrecio": 0},
    ]
    df = parse_history(raw)
    assert list(df["close"]) == [1480.0, 1500.5]
    assert df.index.is_monotonic_increasing


def test_parse_history_fixture():
    df = parse_history(fixture("iol_seriehistorica.json"))
    assert list(df["close"]) == [6461.0, 6435.0, 6520.0]
    assert df["volume"].iloc[-1] == 1520345


def test_parse_positions_filtra_fci():
    raw = {"activos": [
        {"cantidad": 10, "ultimoPrecio": 5000, "titulo": {"simbolo": "GGAL", "tipo": "ACCIONES"}},
        {"cantidad": 100, "ultimoPrecio": 80, "titulo": {"simbolo": "IOLPORA", "tipo": "FondoComundeInversion"}},
    ]}
    assert parse_positions(raw) == {
        "GGAL": {"cantidad": 10, "precio": 5000.0, "ppc": None, "valorizado": None, "tipo": "accion",
                 "moneda": "ARS", "comprometido": 0, "disponible": 10, "unidad_dudosa": False}}


@pytest.mark.parametrize("tipo,esperado", [
    ("ACCIONES", "accion"), ("aCCIONES", "accion"), ("CEDEARS", "cedear"), ("cEDEARS", "cedear"),
    ("TitulosPublicos", "bono"), ("titulosPublicos", "bono"), ("bONOS", "bono"), ("Letras", "letra"),
    ("lETES", "letra"), ("ObligacionesNegociables", "on"), ("oBLIGACIONESPYME", "on"),
    ("FondoComundeInversion", None), ("fONDOSDEINVERSION", None), ("Opciones", None), ("cAUCIONESPESOS", None),
    ("cUPONESOBL", None), ("accionesSuscribibles", None), ("futuros", None), ("", "accion"), (None, "accion"),
])
def test_clasificar_tipo(tipo, esperado):
    assert clasificar_tipo(tipo) == esperado


def test_multiplicador_precio():
    assert multiplicador_precio("accion") == multiplicador_precio("cedear") == 1.0
    assert multiplicador_precio("bono") == multiplicador_precio("letra") == multiplicador_precio("on") == 0.01


def test_parse_positions_fixture_incluye_renta_fija_excluye_fci_opciones():
    pos = parse_positions(fixture("iol_portafolio.json"))
    assert set(pos) == {"GGAL", "YPFD", "AAPL", "AL30", "YCA6O", "S31O6"}
    assert (pos["AL30"]["tipo"], pos["YCA6O"]["tipo"], pos["S31O6"]["tipo"]) == ("bono", "on", "letra")
    # renta fija: cantidad en VN, precio cada 100 VN, valorizado en moneda
    al30 = pos["AL30"]
    assert al30["cantidad"] * al30["precio"] * multiplicador_precio(al30["tipo"]) == al30["valorizado"]
    assert pos["GGAL"] == {"cantidad": 120, "precio": 6520.0, "ppc": 5480.25, "valorizado": 782400.0,
                           "tipo": "accion", "moneda": "ARS", "comprometido": 0, "disponible": 120,
                           "unidad_dudosa": False}
    assert pos["YCA6O"]["moneda"] == "USD"  # ON valuada en dólares: no sumar a pesos sin convertir
    assert pos["YPFD"]["tipo"] == "accion"  # tipo con mayúsculas raras ('aCCIONES')
    assert pos["AAPL"]["tipo"] == "cedear"
    assert isinstance(pos["AAPL"]["cantidad"], int)


def test_parse_positions_vacio_y_sin_tipo():
    assert parse_positions(None) == {}
    assert parse_positions({"activos": [{"cantidad": 0, "titulo": {"simbolo": "X"}}]}) == {}
    sin_tipo = parse_positions({"activos": [{"cantidad": "5", "ultimoPrecio": "1.234,5", "simbolo": "ALUA"}]})
    assert sin_tipo["ALUA"]["cantidad"] == 5 and sin_tipo["ALUA"]["precio"] == 1234.5


def test_parse_cash():
    raw = {"cuentas": [{"moneda": "dolar_Estadounidense", "disponible": 50},
                       {"moneda": "peso_Argentino", "disponible": 123456.7}]}
    assert parse_cash_ars(raw) == 123456.7


def test_parse_cash_fixture_por_plazo():
    raw = fixture("iol_estadocuenta.json")
    assert parse_cash_ars(raw) == 250000.5               # sin plazo: 'disponible' de la cuenta
    assert parse_cash_ars(raw, plazo="t0") == 235000.5   # inmediato
    assert parse_cash_ars(raw, plazo="t1") == 295000.5   # hrs24.disponibleOperar
    assert parse_cash_ars({"cuentas": [{"moneda": "peso_Argentino", "disponible": 10, "saldos": []}]},
                          plazo="t1") == 10.0           # sin saldos: cae a 'disponible'
    assert parse_cash_ars({}) == 0.0


def test_parse_cash_prefiere_cuenta_inversion():
    raw = {"cuentas": [
        {"tipo": "administrada_Argentina_Pesos", "moneda": "peso_Argentino", "disponible": 1},
        {"tipo": "inversion_Argentina_Pesos", "moneda": "peso_Argentino", "disponible": 2},
    ]}
    assert parse_cash_ars(raw) == 2.0


def test_parse_quote_fixture_mejores_puntas():
    q = parse_quote(fixture("iol_cotizacion.json"))
    assert q["ultimoPrecio"] == 6520.0
    assert (q["precioCompra"], q["cantidadCompra"]) == (6515.0, 300)
    assert (q["precioVenta"], q["cantidadVenta"]) == (6525.0, 150)
    assert q["volumen"] == 1520345 and q["montoOperado"] == 9876543210.5
    assert q["fecha"].startswith("2026-10-09")
    assert q["laminaMinima"] == 1 and q["lote"] == 1
    assert parse_quote(None) is None and parse_quote({"puntas": []}) is None


def test_parse_quote_sin_puntas():
    q = parse_quote({"ultimoPrecio": 10, "puntas": None})
    assert q["precioCompra"] is None and q["precioVenta"] is None


def test_parse_panel_fixture():
    panel = parse_panel(fixture("iol_panel_merval.json"))
    assert [p["simbolo"] for p in panel] == ["GGAL", "YPFD", "PAMP"]
    assert panel[0] == {"simbolo": "GGAL", "ultimoPrecio": 6520.0, "volumen": 1520345.0, "montoOperado": None,
                        "descripcion": "Grupo Financiero Galicia"}
    cedears = parse_panel(fixture("iol_cedears_todos.json"))
    assert {c["simbolo"] for c in cedears} == {"AAPL", "SPY"}
    assert parse_panel([{"simbolo": "X", "ultimoPrecio": 1}])[0]["simbolo"] == "X"  # lista suelta
    assert parse_panel(None) == []


def test_parse_operaciones_lista_y_detalle():
    ops = parse_operaciones(fixture("iol_operaciones.json"))
    assert ops[0] == {"numero": 71234567, "fecha": "2026-10-09T11:05:12.47", "simbolo": "GGAL", "tipo": "compra",
                      "estado": "iniciada", "cantidad": 10.0, "precio": 6500.0, "montoOperado": 0.0}
    assert ops[1]["tipo"] == "venta" and ops[1]["montoOperado"] == 194500.0
    det = parse_operaciones(fixture("iol_operacion_detalle.json"))
    assert det[0]["numero"] == 71234567 and det[0]["estado"] == "en_Proceso"
    assert det[0]["fecha"] == "2026-10-09T11:05:12.47"
    assert parse_operaciones(None) == [] and parse_operaciones([{"numero": None}]) == []


def test_parse_order_response():
    ok = parse_order_response(fixture("iol_operar_ok.json"))
    assert ok == {"estado": "enviada", "id": 71234567, "mensaje": "Orden aceptada por IOL."}
    err = parse_order_response(fixture("iol_operar_error.json"))
    assert err["estado"] == "rechazada" and err["id"] is None
    assert "supera el disponible" in err["mensaje"]
    assert parse_order_response(None)["estado"] == "desconocido"


# --- validez -------------------------------------------------------------
AR = timezone.utc  # sólo para construir datetimes aware en UTC


def test_validez_antes_del_cierre_es_hoy():
    # viernes 2026-10-09 14:00 hora AR
    assert validez_cierre_mercado(datetime(2026, 10, 9, 14, 0)) == datetime(2026, 10, 9, 17, 0)


def test_validez_despues_del_cierre_pasa_al_lunes():
    assert validez_cierre_mercado(datetime(2026, 10, 9, 17, 30)) == datetime(2026, 10, 12, 17, 0)


def test_validez_fin_de_semana_y_feriado():
    assert validez_cierre_mercado(datetime(2026, 10, 10, 9, 0)) == datetime(2026, 10, 12, 17, 0)
    feriado = [date(2026, 10, 12)]
    assert validez_cierre_mercado(datetime(2026, 10, 9, 18, 0), feriados=feriado) == datetime(2026, 10, 13, 17, 0)


def test_validez_convierte_desde_utc():
    # 2026-10-09 19:30 UTC = 16:30 AR -> todavía hoy
    assert validez_cierre_mercado(datetime(2026, 10, 9, 19, 30, tzinfo=AR)) == datetime(2026, 10, 9, 17, 0)
    # 20:30 UTC = 17:30 AR -> próximo hábil
    assert validez_cierre_mercado(datetime(2026, 10, 9, 20, 30, tzinfo=AR)) == datetime(2026, 10, 12, 17, 0)


# --- cliente HTTP con sesión falsa ---------------------------------------
class FakeResp:
    def __init__(self, status: int, body=None, headers: dict | None = None):
        self.status_code = status
        self.ok = 200 <= status < 400
        self._body = body
        self.text = json.dumps(body) if body is not None else ""
        self.content = self.text.encode()
        self.headers = headers or {}

    def json(self):
        if self._body is None:
            raise ValueError("sin body")
        return self._body


class FakeSession:
    """Devuelve respuestas de una cola; un Exception en la cola se lanza."""

    def __init__(self, respuestas: list):
        self.respuestas = list(respuestas)
        self.llamadas: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kw):
        self.llamadas.append((method, url, kw))
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def token_ok():
    return FakeResp(200, {"access_token": TOKEN, "refresh_token": "ref-SECRETO", "expires_in": 900})


def cliente(respuestas: list, sleeps: list | None = None) -> tuple[IOLClient, FakeSession]:
    s = FakeSession(respuestas)
    dormidos = sleeps if sleeps is not None else []
    c = IOLClient("persona-anon", PASSWORD, session=s, intervalo_min=0, dormir=dormidos.append)
    return c, s


def test_reintenta_429_y_5xx_con_backoff_exponencial():
    sleeps: list[float] = []
    c, s = cliente([token_ok(), FakeResp(429), FakeResp(503), FakeResp(200, fixture("iol_cotizacion.json"))], sleeps)
    assert c.quote("GGAL")["ultimoPrecio"] == 6520.0
    assert sleeps == [1.0, 2.0]
    assert s.llamadas[-1][1].endswith("/api/v2/bCBA/Titulos/GGAL/Cotizacion")
    assert s.llamadas[-1][2]["headers"]["Authorization"] == f"Bearer {TOKEN}"


def test_respeta_retry_after():
    sleeps: list[float] = []
    c, _ = cliente([token_ok(), FakeResp(429, headers={"Retry-After": "7"}), FakeResp(200, {"titulos": []})], sleeps)
    c.panel()
    assert sleeps == [7.0]


def test_reintenta_errores_de_conexion_y_se_rinde():
    sleeps: list[float] = []
    err = requests.exceptions.ConnectionError("boom")
    c, s = cliente([token_ok(), err, err, err, err], sleeps)
    with pytest.raises(IOLError) as e:
        c.portfolio()
    assert "4 intentos" in str(e.value)
    assert sleeps == [1.0, 2.0, 4.0]  # máx 3 reintentos
    assert TOKEN not in str(e.value) and PASSWORD not in str(e.value)


def test_orden_no_se_reintenta_ante_5xx_ni_error_de_red():
    c, s = cliente([token_ok(), FakeResp(502, {"error": "x"})])
    with pytest.raises(IOLError, match="PUDO haber entrado"):
        c.send_order("COMPRAR", "GGAL", 10, 6500.0)
    assert sum(1 for m, *_ in s.llamadas if m == "POST" and "operar" in _[0]) == 1

    c2, s2 = cliente([token_ok(), requests.exceptions.ReadTimeout("lento")])
    with pytest.raises(IOLError, match="PUDO haber entrado"):
        c2.send_order("VENDER", "GGAL", 10, 6500.0)
    assert len(s2.llamadas) == 2  # token + un solo intento de orden


def test_orden_si_se_reintenta_ante_429():
    sleeps: list[float] = []
    c, s = cliente([token_ok(), FakeResp(429), FakeResp(200, fixture("iol_operar_ok.json"))], sleeps)
    assert c.send_order("COMPRAR", "GGAL", 10, 6500.0)["numeroOperacion"] == 71234567
    payload = s.llamadas[-1][2]["json"]
    assert set(payload) == {"mercado", "simbolo", "cantidad", "precio", "plazo", "validez", "tipoOrden"}
    assert payload["validez"].endswith("T17:00:00")
    assert payload["plazo"] == "t1" and payload["tipoOrden"] == "precioLimite"


def test_errores_no_filtran_token_ni_password():
    cuerpo = {"detalle": f"token {TOKEN} invalido para {PASSWORD}"}
    c, _ = cliente([token_ok(), FakeResp(400, cuerpo)])
    with pytest.raises(IOLError) as e:
        c.account_status()
    msg = str(e.value)
    assert TOKEN not in msg and PASSWORD not in msg and "***" in msg
    assert PASSWORD not in repr(c) and "persona-anon" not in repr(c)


def test_login_fallido_no_muestra_body():
    c, _ = cliente([FakeResp(400, {"error": f"bad password {PASSWORD}"})])
    with pytest.raises(IOLError) as e:
        c.portfolio()
    assert PASSWORD not in str(e.value) and "HTTP 400" in str(e.value)


def test_401_renueva_token_una_vez():
    c, s = cliente([token_ok(), FakeResp(401), token_ok(), FakeResp(200, [])])
    assert c.operaciones(estado="pendientes") == []
    params = s.llamadas[-1][2]["params"]
    assert params == {"filtro.estado": "pendientes", "filtro.pais": "argentina"}


def test_rate_limiter_espera_intervalo_minimo():
    sleeps: list[float] = []
    reloj = iter([0.0, 0.1, 0.25])  # token en t=0; el GET llega en t=0.1
    s = FakeSession([token_ok(), FakeResp(200, {})])
    c = IOLClient("u", "p", session=s, intervalo_min=0.25, dormir=sleeps.append, reloj=lambda: next(reloj))
    c.account_status()
    assert sleeps == [pytest.approx(0.15)]


def test_validaciones_de_orden():
    c, _ = cliente([])
    with pytest.raises(IOLError):
        c.send_order("COMPRA", "GGAL", 1, 1.0)
    with pytest.raises(IOLError):
        c.send_order("COMPRAR", "GGAL", 0, 1.0)
    with pytest.raises(IOLError):
        c.send_order("COMPRAR", "GGAL", 1, 1.0, plazo="t9")
    with pytest.raises(IOLError):
        c.cancelar("abc")


# --- IOLBroker -----------------------------------------------------------
class FakeClient:
    def __init__(self):
        self.enviadas: list[dict] = []

    def portfolio(self):
        return fixture("iol_portafolio.json")

    def account_status(self):
        return fixture("iol_estadocuenta.json")

    def quote(self, simbolo, mercado="bCBA"):
        return fixture("iol_cotizacion.json")

    def operaciones(self, estado=None):
        assert estado == "pendientes"
        return fixture("iol_operaciones.json")[:1]

    def cancelar(self, numero):
        return {"ok": True, "messages": []}

    def send_order(self, lado, simbolo, cantidad, precio, **kw):
        self.enviadas.append({"lado": lado, "simbolo": simbolo, **kw})
        return fixture("iol_operar_ok.json")


def test_iol_broker_end_to_end_con_cliente_falso():
    fc = FakeClient()
    b = IOLBroker(fc, {"ejecucion": {"mercado": "bCBA", "plazo": "t1", "tipo_orden": "precioLimite",
                                     "feriados": ["2026-10-12"]}})
    assert set(b.get_positions()) == {"GGAL", "YPFD", "AAPL", "AL30", "YCA6O", "S31O6"}
    assert b.get_cash_ars() == 295000.5
    assert b.get_quote("GGAL")["precioVenta"] == 6525.0
    assert b.open_orders()[0]["numero"] == 71234567
    assert b.cancel_order(71234567) == {"estado": "cancelada", "id": 71234567, "mensaje": "Orden aceptada por IOL."}
    r = b.place_order("GGAL", "COMPRAR", 10, 6500.0)
    assert r == {"estado": "enviada", "id": 71234567, "mensaje": "Orden aceptada por IOL."}
    assert fc.enviadas[0]["feriados"] == [date(2026, 10, 12)]


def test_iol_broker_settings_faltantes_usa_defaults():
    b = IOLBroker(FakeClient(), {})
    assert (b.mercado, b.plazo, b.tipo_orden, b.feriados) == ("bCBA", "t1", "precioLimite", [])


# --- auditoría: unidades, caja, órdenes inciertas -------------------------
from src.broker.iol import IOLOrdenIncierta  # noqa: E402


def _bono(cantidad, precio, valorizado, **extra):
    return {"activos": [{"cantidad": cantidad, "ultimoPrecio": precio, "valorizado": valorizado, "ppc": 70.0,
                         "titulo": {"simbolo": "AL30", "tipo": "TitulosPublicos", "moneda": "peso_Argentino"},
                         **extra}]}


def test_parse_positions_bono_cotizado_por_unidad_se_pasa_a_cada_100_vn():
    pos = parse_positions(_bono(1000, 866.0, 866000.0))["AL30"]  # 866 por VN: valorizado = cant x precio
    assert pos["precio"] == 86600.0 and pos["ppc"] == 7000.0 and not pos["unidad_dudosa"]
    assert pos["cantidad"] * pos["precio"] * 0.01 == pytest.approx(pos["valorizado"])


def test_parse_positions_bono_con_valorizado_incoherente_queda_marcado():
    pos = parse_positions(_bono(1000, 86600.0, 50.0))["AL30"]
    assert pos["unidad_dudosa"] and pos["precio"] == 86600.0


def test_parse_positions_comprometido_reduce_lo_vendible():
    pos = parse_positions(_bono(1000, 86600.0, 866000.0, comprometido=400))["AL30"]
    assert (pos["comprometido"], pos["disponible"]) == (400, 600)


def test_parse_cash_no_usa_descubierto_ni_negativos():
    saldo = {"liquidacion": "hrs24", "disponible": 100000.0, "disponibleOperar": 600000.0}  # incluye descubierto
    raw = {"cuentas": [{"moneda": "peso_Argentino", "disponible": 100000.0, "saldos": [saldo]}]}
    assert parse_cash_ars(raw, plazo="t1") == 100000.0
    raw_neg = {"cuentas": [{"moneda": "peso_Argentino", "disponible": -5000.0}]}
    assert parse_cash_ars(raw_neg) == 0.0


def test_parse_order_response_2xx_ambiguo_es_incierta():
    assert parse_order_response({})["estado"] == "incierta"
    assert parse_order_response({"messages": [{"description": "x"}]})["estado"] == "incierta"
    assert parse_order_response({"ok": False})["estado"] == "rechazada"


def test_orden_5xx_o_body_ilegible_lanza_incierta():
    c, _ = cliente([token_ok(), FakeResp(502, {"error": "x"})])
    with pytest.raises(IOLOrdenIncierta):
        c.send_order("COMPRAR", "GGAL", 10, 6500.0)
    roto = FakeResp(200, None)
    roto.content = b"<html>"
    c2, _ = cliente([token_ok(), roto])
    with pytest.raises(IOLOrdenIncierta):
        c2.send_order("COMPRAR", "GGAL", 10, 6500.0)
    c3, _ = cliente([token_ok(), FakeResp(400, {"ok": False})])
    with pytest.raises(IOLError) as e:
        c3.send_order("COMPRAR", "GGAL", 10, 6500.0)
    assert not isinstance(e.value, IOLOrdenIncierta)  # 4xx: rechazo definitivo


class _ClienteQueFalla(FakeClient):
    def __init__(self, error):
        super().__init__()
        self.error = error

    def send_order(self, *a, **kw):
        raise self.error


def test_place_order_no_lanza_y_distingue_incierta_de_rechazada():
    b = IOLBroker(_ClienteQueFalla(IOLOrdenIncierta("timeout")), {})
    assert b.place_order("AL30", "COMPRAR", 100, 86600.0, mult=0.01)["estado"] == "incierta"
    b2 = IOLBroker(_ClienteQueFalla(IOLError("HTTP 400")), {})
    assert b2.place_order("AL30", "COMPRAR", 100, 86600.0, mult=0.01)["estado"] == "rechazada"
