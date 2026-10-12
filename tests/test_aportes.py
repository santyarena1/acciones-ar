import pytest

from src.broker.paper import PaperBroker
from src.operador.aportes import detectar_aporte, rendimiento


def test_detecta_deposito():
    assert detectar_aporte(100_000, 300_000, 0, 0, 600_000) == 200_000


def test_ventas_que_se_acreditan_no_son_deposito():
    # la caja sube 150 mil pero hubo ventas por 150 mil que liquidaron
    assert detectar_aporte(100_000, 250_000, 150_000, 0, 600_000) == 0


def test_movimientos_chicos_se_ignoran():
    # 5 mil de un cupón o dividendo: debajo del umbral (máx. de 10 mil y 2% de la cartera)
    assert detectar_aporte(100_000, 105_000, 0, 0, 600_000) == 0


def test_detecta_retiro_sin_ventas_pendientes():
    assert detectar_aporte(300_000, 100_000, 0, 0, 600_000) == -200_000
    assert detectar_aporte(300_000, 100_000, 50_000, 0, 600_000) == 0   # con ventas pendientes no se adivina


def test_primera_vez_no_detecta():
    assert detectar_aporte(None, 500_000, 0, 0, 500_000) == 0


def test_rendimiento_descuenta_aportes():
    g, p = rendimiento(770_000, 700_000)
    assert g == 70_000 and p == pytest.approx(0.10)
    assert rendimiento(100, 0) == (0.0, None)


def test_deposito_en_practica(tmp_path):
    b = PaperBroker(500_000, path=tmp_path / "p.json")
    assert b.depositar(200_000) == 700_000
    with pytest.raises(ValueError):
        b.depositar(-5)
