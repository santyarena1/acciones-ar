"""Tests del operador automático: decisiones puras, horario de BYMA y bitácora (sin red, sin broker real)."""
import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.broker.paper import PaperBroker
from src.operador import bitacora as bmod
from src.operador import decision as d
from src.operador import mercado as m
from src.operador.bitacora import Bitacora, OperadorOcupado

HOY = date(2026, 10, 13)  # martes hábil (el 12/10 es feriado)
FERIADOS = {date(2026, 1, 1), date(2026, 10, 12), date(2026, 11, 23), date(2026, 12, 25)}
COLS = ["ticker", "lado", "cantidad", "precio_ref", "monto_ars", "peso_objetivo", "peso_actual", "mult"]


def ords(*filas) -> pd.DataFrame:
    """filas: (ticker, lado, cantidad, precio_ref[, mult, peso_objetivo, peso_actual])."""
    out = []
    for f in filas:
        t, lado, q, px, *rest = f
        mult = rest[0] if len(rest) > 0 else 1.0
        po = rest[1] if len(rest) > 1 else (0.0 if lado == "VENDER" else 0.05)
        pa = rest[2] if len(rest) > 2 else 0.0
        out.append({"ticker": t, "lado": lado, "cantidad": q, "precio_ref": px, "monto_ars": q * px * mult,
                    "peso_objetivo": po, "peso_actual": pa, "mult": mult})
    return pd.DataFrame(out, columns=COLS)


def costo(df: pd.DataFrame, recargo: float = d.RECARGO_COMPRA_DEFAULT) -> float:
    c = df[df["lado"] == "COMPRAR"]
    return float((c["cantidad"] * c["precio_ref"] * c["mult"] * (1 + recargo)).sum())


# ----------------------------------------------------------------------------- filtrar_por_banda
def test_banda_deja_salidas_y_entradas_y_filtra_ajustes_chicos():
    o = ords(("SAL", "VENDER", 10, 100.0, 1.0, 0.0, 0.05),          # salida
             ("NUE", "COMPRAR", 10, 100.0, 1.0, 0.03, 0.0),         # entrada
             ("AJC", "COMPRAR", 10, 100.0, 1.0, 0.051, 0.05),       # ajuste chico
             ("AJG", "VENDER", 10, 100.0, 1.0, 0.02, 0.06))         # ajuste grande
    out = d.filtrar_por_banda(o, {"SAL": {}, "AJC": {}, "AJG": {}}, 0.02)
    assert dict(zip(out["ticker"], out["motivo"])) == {"SAL": "salida", "NUE": "entrada", "AJG": "ajuste"}


def test_banda_con_vacio_o_none():
    assert d.filtrar_por_banda(None, {}, 0.02).empty
    vacio = d.filtrar_por_banda(ords(), {}, 0.02)
    assert vacio.empty and "motivo" in vacio.columns


def test_banda_peso_objetivo_none_es_salida():
    o = ords(("X", "VENDER", 5, 10.0))
    o["peso_objetivo"] = None
    assert d.filtrar_por_banda(o, {"X": {}}, 0.02)["motivo"].tolist() == ["salida"]


# ----------------------------------------------------------------------------- repetidas
def test_sin_repetidas_por_ticker_y_lado():
    o = ords(("A", "COMPRAR", 1, 1.0), ("A", "VENDER", 1, 1.0), ("B", "COMPRAR", 1, 1.0))
    out = d.sin_repetidas(o, {("A", "COMPRAR")})
    assert list(zip(out["ticker"], out["lado"])) == [("A", "VENDER"), ("B", "COMPRAR")]
    assert d.sin_repetidas(ords(), {("A", "COMPRAR")}).empty


def test_claves_operadas_hoy_desde_el_broker():
    ops = [{"simbolo": "GGAL", "tipo": "compra", "estado": "iniciada", "fecha": "2026-10-13T11:05:12"},
           {"simbolo": "AL30", "tipo": "venta", "estado": "terminada", "fecha": "2026-10-13T12:00:00"},
           {"simbolo": "PAMP", "tipo": "compra", "estado": "rechazada", "fecha": "2026-10-13T12:00:00"},
           {"simbolo": "YPFD", "tipo": "compra", "estado": "terminada", "fecha": "2026-10-09T15:00:00"},
           {"simbolo": "TXAR", "tipo": "Cancelada?", "estado": "x", "fecha": "2026-10-13"}]
    assert d.claves_operadas_hoy(ops, HOY) == {("GGAL", "COMPRAR"), ("AL30", "VENDER")}
    assert d.claves_operadas_hoy(None, HOY) == set()


# ----------------------------------------------------------------------------- precio_sano
Q = {"ultimoPrecio": 100.0, "precioCompra": 99.5, "precioVenta": 100.5, "fecha": "2026-10-13T12:00:00"}


def test_precio_sano_dentro_y_fuera_de_tolerancia():
    assert d.precio_sano(100.0, {**Q, "ultimoPrecio": 104.0}, 0.05) == (True, 104.0)
    assert d.precio_sano(100.0, {**Q, "ultimoPrecio": 106.0}, 0.05) == (False, 106.0)


def test_precio_sano_bonos_misma_unidad_cada_100_vn():
    # análisis AL30 86.600 (cada 100 VN); si el broker diera 866 (por VN) es otra unidad: no operar
    assert d.precio_sano(86600.0, {"ultimoPrecio": 86900.0}, 0.05)[0]
    assert not d.precio_sano(86600.0, {"ultimoPrecio": 866.0}, 0.05)[0]


def test_precio_sano_sin_cotizacion_paper_vs_real():
    assert d.precio_sano(100.0, None, 0.05) == (True, 100.0)              # paper: usa el del análisis
    assert d.precio_sano(100.0, None, 0.05, exigir=True) == (False, 100.0)  # real: no opera a ciegas
    assert d.precio_sano(100.0, {"ultimoPrecio": None}, 0.05, exigir=True)[0] is False


def test_precio_sano_precio_de_analisis_roto():
    assert d.precio_sano(0.0, Q, 0.05)[0] is False
    assert d.precio_sano(float("nan"), Q, 0.05)[0] is False
    assert d.precio_sano(100.0, {**Q, "ultimoPrecio": -1.0}, 0.05)[0] is False


def test_precio_sano_cotizacion_de_otro_dia_no_sirve():
    viejo = {**Q, "fecha": "2026-10-09T16:59:00"}
    assert d.precio_sano(100.0, viejo, 0.05, hoy=HOY)[0] is False
    assert d.precio_sano(100.0, Q, 0.05, hoy=HOY)[0] is True


def test_precio_sano_controla_la_punta_del_lado():
    libro_roto = {**Q, "precioVenta": 130.0, "precioCompra": 70.0}
    assert d.precio_sano(100.0, libro_roto, 0.05, lado="COMPRAR")[0] is False
    assert d.precio_sano(100.0, libro_roto, 0.05, lado="VENDER")[0] is False
    assert d.precio_sano(100.0, Q, 0.05, lado="COMPRAR") == (True, 100.0)
    sin_ask = {**Q, "precioVenta": None}
    assert d.precio_sano(100.0, sin_ask, 0.05, lado="COMPRAR")[0] is True
    assert d.precio_sano(100.0, sin_ask, 0.05, lado="COMPRAR", exigir=True)[0] is False


# ----------------------------------------------------------------------------- láminas
@pytest.mark.parametrize("q,lam,inc,esperado", [
    (150, 1, 1, 150), (150, 100, 1, 150), (99, 100, 1, 0), (1550, 1000, 1000, 1000), (999, 1000, 1000, 0),
    (-5, 1, 1, 0), (7, 1, 5, 5),
])
def test_redondear_compra(q, lam, inc, esperado):
    assert d.redondear_a_lamina(q, lam, inc) == esperado


def test_redondear_venta_nunca_supera_tenencia_y_no_deja_remanente_invendible():
    assert d.redondear_a_lamina(500, 1, 1, tenencia=300, lado="VENDER") == 300      # vender todo vale
    assert d.redondear_a_lamina(1500, 1000, 1, tenencia=1500, lado="VENDER") == 1500
    # vender 1400 de 1500 dejaría 100 < lámina 1000: se vende 500 y queda una lámina... pero 500 < lámina -> 0
    assert d.redondear_a_lamina(1400, 1000, 1, tenencia=1500, lado="VENDER") == 0
    assert d.redondear_a_lamina(2500, 1000, 1, tenencia=3000, lado="VENDER") == 2000
    assert d.redondear_a_lamina(10, 1, 1, tenencia=0, lado="VENDER") == 0


def test_laminas_de_cotizaciones():
    out = d.laminas_de_cotizaciones({"YM34O": {"laminaMinima": 1000.0, "lote": 1.0}, "GGAL": {"laminaMinima": None},
                                     "X": None})
    assert out == {"YM34O": (1000, 1), "GGAL": (1, 1)}


def test_ajustar_ventas_limita_a_lo_disponible():
    o = ords(("AL30", "VENDER", 1000, 86600.0, 0.01), ("GGAL", "VENDER", 50, 6500.0), ("NADA", "VENDER", 5, 1.0),
             ("B", "COMPRAR", 1, 1.0))
    pos = {"AL30": {"cantidad": 1000, "disponible": 600}, "GGAL": {"cantidad": 40}}
    out = d.ajustar_ventas(o, pos).set_index("ticker")
    assert out.loc["AL30", "cantidad"] == 600 and out.loc["AL30", "monto_ars"] == round(600 * 866.0)
    assert out.loc["GGAL", "cantidad"] == 40
    assert "NADA" not in out.index and "B" in out.index


# ----------------------------------------------------------------------------- ajustar_a_caja
def test_caja_nunca_se_excede_contando_slippage_y_comision():
    o = ords(("A", "COMPRAR", 100, 1000.0), ("B", "COMPRAR", 100, 1000.0))
    out, faltante = d.ajustar_a_caja(o, 150_000, {"A": 80, "B": 60})
    assert costo(out) <= 150_000
    assert out.set_index("ticker").loc["A", "cantidad"] == 100      # la de mayor score entra entera
    assert faltante == pytest.approx((200 - out["cantidad"].sum()) * 1000.0)


def test_caja_con_paper_broker_ninguna_compra_rechazada_por_caja(tmp_path):
    # el broker de práctica cobra comisión 0,6% y el límite es último +0,5%: todo tiene que entrar
    caja = 1_000_000.0
    o = ords(("A", "COMPRAR", 300, 1500.0), ("B", "COMPRAR", 400, 1200.0), ("AL30", "COMPRAR", 1000, 86600.0, 0.01))
    out, _ = d.ajustar_a_caja(o, caja, {"A": 90, "B": 70, "AL30": 80}, recargo=0.005 + 0.006)
    b = PaperBroker(caja, path=tmp_path / "p.json", comision=0.006)
    for _, f in out.iterrows():
        px = math.floor(f["precio_ref"] * 1.005 * 100) / 100
        r = b.place_order(f["ticker"], "COMPRAR", int(f["cantidad"]), px, mult=float(f["mult"]))
        assert r["estado"].startswith("ejecutada"), r
    assert b.get_cash_ars() >= 0


def test_caja_respeta_mult_de_renta_fija():
    o = ords(("AL30", "COMPRAR", 1000, 86600.0, 0.01))                  # 1000 VN = $866.000
    out, _ = d.ajustar_a_caja(o, 500_000, {}, recargo=0.0)
    assert out.loc[0, "cantidad"] == 577 and costo(out, 0.0) <= 500_000   # floor(500000 / 866)


def test_caja_respeta_laminas():
    o = ords(("YM34O", "COMPRAR", 5000, 160000.0, 0.01))
    out, faltante = d.ajustar_a_caja(o, 2_500_000, {}, recargo=0.0, laminas={"YM34O": (1000, 1000)})
    assert out.loc[0, "cantidad"] == 1000                                 # 1562 VN alcanzan -> 1 lámina
    out2, _ = d.ajustar_a_caja(o, 1_000_000, {}, recargo=0.0, laminas={"YM34O": (1000, 1000)})
    assert out2.empty                                                     # no alcanza ni una lámina


def test_caja_negativa_o_nan_no_compra_nada_y_ventas_pasan():
    o = ords(("V", "VENDER", 10, 100.0), ("A", "COMPRAR", 10, 100.0))
    for caja in (-50_000.0, float("nan"), 0.0):
        out, faltante = d.ajustar_a_caja(o, caja, {"A": 1})
        assert list(out["lado"]) == ["VENDER"] and faltante == 1000.0


def test_caja_no_cuenta_la_plata_de_las_ventas():
    o = ords(("V", "VENDER", 100, 1000.0), ("A", "COMPRAR", 100, 1000.0))
    out, _ = d.ajustar_a_caja(o, 0.0, {})
    assert list(out["ticker"]) == ["V"]


def test_caja_precio_roto_no_rompe_ni_compra():
    o = ords(("A", "COMPRAR", 10, float("nan")), ("B", "COMPRAR", 10, 0.0), ("C", "COMPRAR", 10, 100.0))
    out, _ = d.ajustar_a_caja(o, 10_000, {})
    assert list(out["ticker"]) == ["C"]


def test_caja_prioridad_nan_al_final_y_empates_estables():
    o = ords(("N", "COMPRAR", 10, 100.0), ("X", "COMPRAR", 10, 100.0), ("Y", "COMPRAR", 10, 100.0))
    out, _ = d.ajustar_a_caja(o, 2000, {"N": float("nan"), "X": 50, "Y": 50}, recargo=0.0)
    assert list(out["ticker"]) == ["X", "Y"]


def test_caja_descarta_compras_achicadas_debajo_del_minimo():
    o = ords(("A", "COMPRAR", 100, 1000.0), ("B", "COMPRAR", 100, 1000.0))
    out, faltante = d.ajustar_a_caja(o, 120_000, {"A": 2, "B": 1}, recargo=0.0, monto_minimo=50_000)
    assert list(out["ticker"]) == ["A"]          # a B le quedarían $20.000: no vale la comisión
    assert faltante == 100_000                   # B entera queda como faltante


def test_caja_vacio():
    out, f = d.ajustar_a_caja(ords(), 1000, {})
    assert out.empty and f == 0.0


# ----------------------------------------------------------------------------- pedido de fondos
def test_pedido_de_fondos():
    ranking = pd.DataFrame({"senal": ["AGREGAR", "MANTENER"], "dist_max_52s": [-0.2, -0.3]}, index=["A", "B"])
    s = {"operador": {"pedido_fondos_minimo": 100_000}}
    p = d.pedido_de_fondos(250_000, ranking, {"A": {}, "B": {}}, s)
    assert p["monto"] == 250_000 and p["recompras"] == ["A (-20% desde su máximo, el análisis sigue positivo)"]
    assert d.pedido_de_fondos(50_000, ranking, {}, s) is None
    assert d.pedido_de_fondos(float("nan"), ranking, {}, s) is None
    assert d.pedido_de_fondos(500_000, pd.DataFrame(), {"A": {}}, s)["recompras"] == []


# ----------------------------------------------------------------------------- mercado
def test_mercado_abierto_horario_y_margen():
    assert not m.mercado_abierto(datetime(2026, 10, 13, 11, 2), FERIADOS)
    assert m.mercado_abierto(datetime(2026, 10, 13, 11, 5), FERIADOS)
    assert m.mercado_abierto(datetime(2026, 10, 13, 16, 54), FERIADOS)
    assert not m.mercado_abierto(datetime(2026, 10, 13, 16, 55), FERIADOS)
    assert m.mercado_abierto(datetime(2026, 10, 13, 16, 59), FERIADOS, margen_min=0)
    assert not m.mercado_abierto(datetime(2026, 10, 13, 17, 0), FERIADOS, margen_min=0)
    assert m.mercado_abierto(datetime(2026, 10, 13, 12, 30), FERIADOS, margen_min=75)   # márgenes > 60 min
    assert not m.mercado_abierto(datetime(2026, 10, 13, 12, 0), FERIADOS, margen_min=75)


def test_mercado_cerrado_feriado_y_fin_de_semana():
    assert not m.mercado_abierto(datetime(2026, 10, 12, 12, 0), FERIADOS)   # feriado
    assert not m.mercado_abierto(datetime(2026, 10, 10, 12, 0), FERIADOS)   # sábado


def test_mercado_sin_calendario_no_opera():
    assert not m.mercado_abierto(datetime(2026, 10, 13, 12, 0), set())
    assert m.mercado_abierto(datetime(2026, 10, 13, 12, 0), set(), exigir_calendario=False)


def test_mercado_convierte_horas_con_zona():
    utc = datetime(2026, 10, 13, 14, 30, tzinfo=timezone.utc)          # 11:30 en Buenos Aires
    assert m.mercado_abierto(utc, FERIADOS)
    assert not m.mercado_abierto(datetime(2026, 10, 13, 20, 30, tzinfo=timezone.utc), FERIADOS)  # 17:30 AR


def test_ahora_ar_es_hora_argentina_aunque_la_pc_este_en_otra_zona(monkeypatch):
    real = datetime.now(timezone.utc)
    esperado = (real - timedelta(hours=3)).replace(tzinfo=None)
    assert abs((m.ahora_ar() - esperado).total_seconds()) < 5
    from src.broker import iol
    monkeypatch.setattr(iol, "_TZ_NOMBRE", "Zona/Inexistente")          # sin tzdata: UTC-3 fijo
    assert iol.tz_argentina().utcoffset(None) == timedelta(hours=-3)


# ----------------------------------------------------------------------------- bitácora
def test_bitacora_registra_en_hora_argentina(tmp_path):
    ev = Bitacora(tmp_path).registrar("x")
    assert ev["ts"].endswith("-03:00")


def _orden(bit: Bitacora, ticker: str, lado: str, estado: str, ts: str | None = None) -> None:
    ev = bit.registrar("orden", ticker=ticker, lado=lado, estado=estado)
    if ts:  # reescribe el ts del último evento
        lineas = bit.archivo.read_text(encoding="utf-8").splitlines()
        lineas[-1] = json.dumps({**ev, "ts": ts})
        bit.archivo.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def test_ordenes_del_dia_bloquea_todo_menos_rechazos(tmp_path):
    bit = Bitacora(tmp_path)
    hoy = m.hoy_ar()
    _orden(bit, "A", "COMPRAR", "enviada")
    _orden(bit, "B", "COMPRAR", "rechazada")
    _orden(bit, "C", "VENDER", "error")          # timeout: pudo haber entrado
    _orden(bit, "D", "COMPRAR", "incierta")
    _orden(bit, "E", "COMPRAR", "ejecutada (paper)")
    assert bit.ordenes_del_dia(hoy) == {("A", "COMPRAR"), ("C", "VENDER"), ("D", "COMPRAR"), ("E", "COMPRAR")}


def test_intento_sin_respuesta_bloquea_y_rechazo_posterior_libera(tmp_path):
    bit = Bitacora(tmp_path)
    hoy = m.hoy_ar()
    bit.registrar_intento("A", "COMPRAR", cantidad=10)        # el proceso murió después de enviar
    bit.registrar_intento("B", "COMPRAR", cantidad=10)
    _orden(bit, "B", "COMPRAR", "rechazada")
    assert bit.ordenes_del_dia(hoy) == {("A", "COMPRAR")}


def test_ordenes_de_otro_dia_no_bloquean(tmp_path):
    bit = Bitacora(tmp_path)
    _orden(bit, "A", "COMPRAR", "enviada", ts="2026-10-09T16:00:00-03:00")
    assert bit.ordenes_del_dia(date(2026, 10, 13)) == set()
    assert bit.ordenes_del_dia(date(2026, 10, 9)) == {("A", "COMPRAR")}


def test_eventos_tolera_lineas_rotas(tmp_path):
    bit = Bitacora(tmp_path)
    bit.registrar("a")
    with open(bit.archivo, "a", encoding="utf-8") as f:
        f.write("{roto\n[1,2]\n")
    bit.registrar("b")
    assert [e["tipo"] for e in bit.eventos()] == ["a", "b"]
    assert bit.eventos(tipo="b")[0]["tipo"] == "b" and len(bit.eventos(ultimos=1)) == 1


def test_estado_pausa_reanuda_y_estado_roto_pausa(tmp_path):
    bit = Bitacora(tmp_path)
    assert bit.estado()["pausado"] is False
    bit.pausar("prueba")
    assert bit.estado() == {"pausado": True, "ultimo_rebalanceo": None, "motivo_pausa": "prueba"}
    bit.reanudar()
    assert bit.estado()["pausado"] is False
    bit.estado_path.write_text("{no es json", encoding="utf-8")
    assert bit.estado()["pausado"] is True                              # falla cerrado
    assert not list(tmp_path.glob("*.tmp"))


def test_candado_excluye_corridas_simultaneas(tmp_path):
    bit = Bitacora(tmp_path)
    with bit.candado():
        with pytest.raises(OperadorOcupado):
            with Bitacora(tmp_path).candado():
                pass
    assert not bit.candado_path.exists()
    with bit.candado():                                                 # se libera al salir
        pass


def test_candado_abandonado_se_reemplaza(tmp_path):
    bit = Bitacora(tmp_path)
    bit.candado_path.write_text("123 viejo", encoding="utf-8")
    viejo = time.time() - 2 * bmod.CANDADO_VENCE_SEG
    os.utime(bit.candado_path, (viejo, viejo))
    with bit.candado():
        assert bit.candado_path.read_text(encoding="utf-8").split()[0] == str(os.getpid())
    assert any(e["tipo"] == "aviso" for e in bit.eventos())


def test_candado_se_libera_si_la_corrida_falla(tmp_path):
    bit = Bitacora(tmp_path)
    with pytest.raises(ValueError):
        with bit.candado():
            raise ValueError("boom")
    assert not bit.candado_path.exists()
