from src.broker.iol import parse_cash_ars, parse_history, parse_positions


def test_parse_history():
    raw = [
        {"fechaHora": "2026-10-09T17:00:00", "ultimoPrecio": 1500.5, "volumenNominal": 1000},
        {"fechaHora": "2026-10-08T17:00:00", "ultimoPrecio": 1480.0, "volumenNominal": 900},
        {"fechaHora": "2026-10-07T17:00:00", "ultimoPrecio": 0},
    ]
    df = parse_history(raw)
    assert list(df["close"]) == [1480.0, 1500.5]
    assert df.index.is_monotonic_increasing


def test_parse_positions_filtra_no_acciones():
    raw = {"activos": [
        {"cantidad": 10, "ultimoPrecio": 5000, "titulo": {"simbolo": "GGAL", "tipo": "ACCIONES"}},
        {"cantidad": 100, "ultimoPrecio": 80, "titulo": {"simbolo": "AL30", "tipo": "TitulosPublicos"}},
    ]}
    assert parse_positions(raw) == {"GGAL": {"cantidad": 10, "precio": 5000.0}}


def test_parse_cash():
    raw = {"cuentas": [{"moneda": "dolar_Estadounidense", "disponible": 50},
                       {"moneda": "peso_Argentino", "disponible": 123456.7}]}
    assert parse_cash_ars(raw) == 123456.7
