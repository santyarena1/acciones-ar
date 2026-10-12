"""Tests del broker simulado (ppc, comisión, persistencia, rechazos, renta fija)."""
import json

import pytest

from src.broker.paper import PaperBroker


def test_paper_broker_basico_con_comision(tmp_path):
    # (movido desde test_backtest_paper.py y ajustado a la comisión)
    b = PaperBroker(100_000, path=tmp_path / "s.json")
    assert b.place_order("GGAL", "COMPRAR", 10, 5000)["estado"].startswith("ejecutada")
    assert b.get_cash_ars() == pytest.approx(100_000 - 50_000 * 1.006)
    assert b.place_order("GGAL", "VENDER", 20, 5000)["estado"] == "rechazada"
    b2 = PaperBroker(0, path=tmp_path / "s.json")  # persiste
    assert b2.get_positions()["GGAL"]["cantidad"] == 10


def test_sin_comision(tmp_path):
    b = PaperBroker(100_000, path=tmp_path / "s.json", comision=0.0)
    b.place_order("GGAL", "COMPRAR", 10, 5000)
    assert b.get_cash_ars() == 50_000


def test_ppc_ponderado_y_venta_no_lo_cambia(tmp_path):
    b = PaperBroker(1_000_000, path=tmp_path / "s.json", comision=0.01)
    b.place_order("GGAL", "COMPRAR", 10, 1000)
    b.place_order("GGAL", "COMPRAR", 30, 2000)
    pos = b.get_positions()["GGAL"]
    assert pos["ppc"] == pytest.approx((10 * 1000 + 30 * 2000) / 40)
    assert pos == {**pos, "cantidad": 40, "precio": 2000.0, "valorizado": 80_000.0, "tipo": "accion"}
    caja_antes = b.get_cash_ars()
    r = b.place_order("GGAL", "VENDER", 15, 3000)
    assert r["estado"].startswith("ejecutada") and r["id"]
    assert b.get_cash_ars() == pytest.approx(caja_antes + 45_000 * 0.99)
    assert b.get_positions()["GGAL"]["ppc"] == pytest.approx(1750.0)
    b.place_order("GGAL", "VENDER", 25, 3000)
    assert "GGAL" not in b.get_positions()


def test_rechazos(tmp_path):
    b = PaperBroker(10_000, path=tmp_path / "s.json")
    r = b.place_order("GGAL", "COMPRAR", 2, 5000)  # 10.000 + comisión > caja
    assert r == {"estado": "rechazada", "id": None, "mensaje": r["mensaje"]}
    assert "caja insuficiente" in r["mensaje"]
    assert b.place_order("GGAL", "COMPRA", 1, 10)["estado"] == "rechazada"
    assert b.place_order("GGAL", "COMPRAR", 0, 10)["estado"] == "rechazada"
    assert b.place_order("GGAL", "COMPRAR", 1, -5)["estado"] == "rechazada"
    assert b.place_order("GGAL", "COMPRAR", 1, 10, mult=0)["estado"] == "rechazada"
    assert b.place_order("GGAL", "VENDER", 1, 10)["estado"] == "rechazada"
    assert b.get_cash_ars() == 10_000 and b.historial() == []
    assert not (tmp_path / "s.json").exists()  # un rechazo no persiste nada


def test_renta_fija_con_multiplicador(tmp_path):
    b = PaperBroker(2_000_000, path=tmp_path / "s.json", comision=0.0)
    # AL30: 1000 VN a $75.800 cada 100 VN -> $758.000
    r = b.place_order("AL30", "COMPRAR", 1000, 75_800, mult=0.01, tipo="bono")
    assert r["estado"].startswith("ejecutada")
    assert b.get_cash_ars() == pytest.approx(2_000_000 - 758_000)
    pos = b.get_positions()["AL30"]
    assert pos["tipo"] == "bono" and pos["ppc"] == 75_800 and pos["valorizado"] == pytest.approx(758_000)
    assert b.historial()[-1]["monto"] == 758_000


def test_persistencia_atomica_e_historial(tmp_path):
    path = tmp_path / "sub" / "s.json"
    b = PaperBroker(100_000, path=path)
    b.place_order("ALUA", "COMPRAR", 10, 1000)
    assert [p.name for p in path.parent.iterdir()] == ["s.json"]  # sin temporales colgados
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["historial"][0]["ticker"] == "ALUA" and data["historial"][0]["comision"] == 60.0
    b2 = PaperBroker(0, path=path)
    assert b2.get_positions()["ALUA"]["ppc"] == 1000.0
    assert b2.historial()[0]["id"] == "paper-1"


def test_compatible_con_json_viejo(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"caja": 5000.0, "posiciones": {"GGAL": {"cantidad": 3, "precio": 1000.0}},
                                "historial": []}), encoding="utf-8")
    b = PaperBroker(999, path=path, comision=0.0)
    assert b.get_cash_ars() == 5000.0
    assert b.get_positions()["GGAL"] == {"cantidad": 3, "precio": 1000.0, "ppc": None, "valorizado": 3000.0,
                                         "tipo": "accion"}
    b.place_order("GGAL", "COMPRAR", 1, 2000)  # sin ppc previo: usa el precio guardado
    assert b.get_positions()["GGAL"]["ppc"] == pytest.approx((3 * 1000 + 2000) / 4)


def test_json_corrupto_da_error_claro(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{no es json", encoding="utf-8")
    with pytest.raises(ValueError, match="estado paper"):
        PaperBroker(0, path=path)


def test_comision_invalida(tmp_path):
    with pytest.raises(ValueError):
        PaperBroker(0, path=tmp_path / "s.json", comision=-0.1)


def test_defaults_del_abc(tmp_path):
    b = PaperBroker(0, path=tmp_path / "s.json")
    assert b.get_quote("GGAL") is None and b.open_orders() == []
    assert b.cancel_order("x")["estado"] == "no_soportado"
