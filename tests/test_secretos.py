"""Secretos cifrados compatibles con la web (AES-256-GCM, 'v1:' + base64(nonce || ct || tag))."""
import base64
import json
import os

import pytest

from src import db
from src import secretos as s

VECTOR = json.loads((db.SCHEMA_SQL.parent / "vector_cifrado.json").read_text(encoding="utf-8"))
CLAVE = base64.b64decode(VECTOR["clave_base64"])


def test_vector_fijo_compatible_con_la_web():
    valor = s.cifrar(VECTOR["texto"], CLAVE, bytes.fromhex(VECTOR["nonce_hex"]))
    assert valor == VECTOR["valor"]
    assert s.descifrar(VECTOR["valor"], CLAVE) == VECTOR["texto"]
    crudo = base64.b64decode(valor[3:])
    assert len(crudo) == 12 + len(VECTOR["texto"].encode()) + 16      # nonce || ciphertext || tag


def test_cifrado_normal_usa_nonce_aleatorio():
    a, b = s.cifrar("x", CLAVE), s.cifrar("x", CLAVE)
    assert a != b and s.descifrar(a, CLAVE) == s.descifrar(b, CLAVE) == "x"


@pytest.mark.parametrize("valor", ["sin-prefijo", "v1:%%%", "v1:" + base64.b64encode(b"corto").decode()])
def test_formatos_rotos(valor):
    with pytest.raises(s.SecretoIlegible):
        s.descifrar(valor, CLAVE)


def test_clave_equivocada_o_dato_alterado_no_filtra_el_valor():
    valor = s.cifrar("clave-super-secreta", CLAVE)
    with pytest.raises(s.SecretoIlegible) as e:
        s.descifrar(valor, bytes(32))
    assert "clave-super-secreta" not in str(e.value)


def test_clave_de_entorno_valida(monkeypatch):
    with pytest.raises(s.SecretoIlegible):
        s.clave_de_entorno()
    monkeypatch.setenv("CLAVE_CIFRADO", base64.b64encode(b"corta").decode())
    with pytest.raises(s.SecretoIlegible):
        s.clave_de_entorno()
    monkeypatch.setenv("CLAVE_CIFRADO", VECTOR["clave_base64"])
    assert s.clave_de_entorno() == CLAVE


def test_cargar_secretos_en_entorno(base_sqlite, monkeypatch):
    monkeypatch.setenv("CLAVE_CIFRADO", VECTOR["clave_base64"])
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "del-env-local")
    filas = {"IOL_USERNAME": s.cifrar("usuario", CLAVE), "IOL_PASSWORD": s.cifrar("clave", CLAVE),
             "TELEGRAM_CHAT_ID": s.cifrar("123", CLAVE), "TELEGRAM_TOKEN": "v1:roto", "OTRA": s.cifrar("z", CLAVE)}
    with base_sqlite.begin() as conn:
        for k, v in filas.items():
            conn.execute(db.secretos.insert().values(clave=k, valor=v, actualizado=db.ahora_utc()))
    for nombre in ("IOL_USERNAME", "IOL_PASSWORD", "TELEGRAM_TOKEN"):
        monkeypatch.delenv(nombre, raising=False)
    cargados = s.cargar_secretos_en_entorno()
    assert cargados == ["IOL_USERNAME", "IOL_PASSWORD"]
    assert os.environ["IOL_USERNAME"] == "usuario" and os.environ["IOL_PASSWORD"] == "clave"
    assert os.environ["TELEGRAM_CHAT_ID"] == "del-env-local"          # el entorno local manda
    assert "TELEGRAM_TOKEN" not in os.environ and "OTRA" not in os.environ


def test_sin_base_no_carga_nada():
    assert s.cargar_secretos_en_entorno() == []
