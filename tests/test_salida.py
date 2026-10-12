"""Modo silencioso (logs públicos de GitHub Actions): solo líneas genéricas, nada de montos, tickers ni errores."""
import logging
import re
import sys
import warnings

import pytest

import main as cli
from src import salida
from src.operador import ejecutor as ej

SENSIBLE = ("GGAL", "YPFD", "1.234.567", "1234567", "987", "clave", "Traceback")


def _resultado_con_detalles(*a, **k):
    print("Comprando GGAL por $1.234.567")                     # prints internos del análisis
    print("aviso con clave", file=sys.stderr)
    logging.getLogger("x").error("caja 987")
    warnings.warn("YPFD 987")
    return ej.Resultado("operó", "C 10 GGAL, V 5 YPFD", [{"ticker": "GGAL"}, {"ticker": "YPFD"}],
                        {"monto": 1234567, "texto": "faltan $1.234.567"}, "20261012_1130")


def _sin_digitos_salvo_conteos(texto: str) -> str:
    return re.sub(r"\b\d+ (órdenes|nuevos)\b", "", texto)


def test_operar_silencioso_solo_imprime_estado_generico(monkeypatch, capsys):
    monkeypatch.setenv("SALIDA_SILENCIOSA", "1")
    monkeypatch.setattr(ej, "operar", _resultado_con_detalles)
    with pytest.raises(SystemExit) as e:
        cli.main(["operar"])
    assert e.value.code == 0
    out, err = capsys.readouterr()
    assert out.strip() == "[ok] corrida guardada; 2 órdenes; hay un pedido de fondos"
    assert err == ""
    assert not any(x in out for x in SENSIBLE)
    assert not re.search(r"\d", _sin_digitos_salvo_conteos(out))


def test_falla_inesperada_silenciosa_no_muestra_el_error(monkeypatch, capsys):
    monkeypatch.setenv("SALIDA_SILENCIOSA", "1")

    def explota(*a, **k):
        raise RuntimeError("login falló para usuario@ejemplo.com con clave 1234567")
    monkeypatch.setattr(ej, "operar", explota)
    with pytest.raises(SystemExit) as e:
        cli.main(["operar"])
    out, err = capsys.readouterr()
    assert e.value.code == 1 and out.strip() == "[error] falla inesperada (detalle en la bitácora)"
    assert "usuario" not in out + err and "1234567" not in out + err


def test_sin_modo_silencioso_imprime_el_detalle(monkeypatch, capsys):
    monkeypatch.setattr(ej, "operar", _resultado_con_detalles)
    with pytest.raises(SystemExit):
        cli.main(["operar"])
    assert "GGAL" in capsys.readouterr().out


def test_db_init_sin_base(monkeypatch, capsys):
    monkeypatch.setenv("SALIDA_SILENCIOSA", "1")
    with pytest.raises(SystemExit) as e:
        cli.main(["db-init"])
    assert e.value.code == 1 and "falta DATABASE_URL" in capsys.readouterr().out


def test_db_init_con_base(base_sqlite, monkeypatch, capsys):
    monkeypatch.setenv("SALIDA_SILENCIOSA", "1")
    cli.main(["db-init"])
    assert capsys.readouterr().out.startswith("[ok] esquema aplicado")


@pytest.mark.parametrize("estado", ["operó", "sin_cambios", "analizado", "cerrado", "pausado", "ocupado", "error"])
def test_lineas_genericas(estado):
    linea = salida.linea_operar(estado, 3, False)
    assert linea.startswith("[") and not re.search(r"\d", linea.replace("3 órdenes", ""))


def test_silenciar_restaura_la_salida(monkeypatch, capsys):
    monkeypatch.setenv("SALIDA_SILENCIOSA", "1")
    with salida.silenciar():
        print("oculto")
        salida.estado("[ok] visible")
    print("después")
    assert capsys.readouterr().out == "[ok] visible\ndespués\n"
    assert logging.root.manager.disable == 0
