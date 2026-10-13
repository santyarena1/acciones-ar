import importlib.util
from pathlib import Path


def _modulo():
    ruta = Path(__file__).resolve().parent.parent / "api" / "operar.py"
    spec = importlib.util.spec_from_file_location("api_operar", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_sin_secreto_configurado_rechaza_todo(monkeypatch):
    monkeypatch.delenv("CRON_SECRET", raising=False)
    assert not _modulo()._autorizado("Bearer cualquiera")


def test_solo_acepta_el_secreto_exacto(monkeypatch):
    monkeypatch.setenv("CRON_SECRET", "s3creto-largo")
    m = _modulo()
    assert m._autorizado("Bearer s3creto-largo")
    assert not m._autorizado("Bearer otro") and not m._autorizado("") and not m._autorizado("s3creto-largo")
