"""Secretos cifrados en la base (tabla `secretos`), compatibles con la web (Node).

Formato: valor = 'v1:' + base64(nonce[12] || ciphertext || tag[16]) con AES-256-GCM, sin datos asociados.
Clave: base64 de 32 bytes en la variable de entorno CLAVE_CIFRADO (la misma en Vercel y en GitHub Actions).
En Node equivale a createCipheriv('aes-256-gcm', clave, nonce) con el authTag pegado al final.

Nunca se loguean ni se meten en excepciones los valores descifrados.
"""
from __future__ import annotations

import base64
import binascii
import logging
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENV_CLAVE = "CLAVE_CIFRADO"
PREFIJO = "v1:"
NONCE_BYTES, TAG_BYTES, CLAVE_BYTES = 12, 16, 32
SECRETOS_ENTORNO = ("IOL_USERNAME", "IOL_PASSWORD", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")

log = logging.getLogger(__name__)


class SecretoIlegible(ValueError):
    """El valor no se pudo descifrar (clave equivocada, dato roto o formato desconocido)."""


def clave_de_entorno() -> bytes:
    crudo = os.getenv(ENV_CLAVE, "").strip()
    if not crudo:
        raise SecretoIlegible("Falta CLAVE_CIFRADO.")
    try:
        clave = base64.b64decode(crudo, validate=True)
    except (binascii.Error, ValueError):
        raise SecretoIlegible("CLAVE_CIFRADO no es base64 válido.") from None
    if len(clave) != CLAVE_BYTES:
        raise SecretoIlegible("CLAVE_CIFRADO tiene que tener 32 bytes.")
    return clave


def cifrar(texto: str, clave: bytes, nonce: bytes | None = None) -> str:
    """`nonce` fijo solo para vectores de prueba: en uso normal siempre es aleatorio."""
    nonce = nonce if nonce is not None else os.urandom(NONCE_BYTES)
    if len(nonce) != NONCE_BYTES:
        raise ValueError("El nonce tiene que tener 12 bytes.")
    sellado = AESGCM(clave).encrypt(nonce, texto.encode("utf-8"), None)   # ciphertext || tag
    return PREFIJO + base64.b64encode(nonce + sellado).decode("ascii")


def descifrar(valor: str, clave: bytes) -> str:
    if not isinstance(valor, str) or not valor.startswith(PREFIJO):
        raise SecretoIlegible("Formato de secreto desconocido.")
    try:
        crudo = base64.b64decode(valor[len(PREFIJO):], validate=True)
    except (binascii.Error, ValueError):
        raise SecretoIlegible("Secreto con base64 inválido.") from None
    if len(crudo) < NONCE_BYTES + TAG_BYTES:
        raise SecretoIlegible("Secreto demasiado corto.")
    try:
        plano = AESGCM(clave).decrypt(crudo[:NONCE_BYTES], crudo[NONCE_BYTES:], None)
    except InvalidTag:
        raise SecretoIlegible("No se pudo descifrar (clave equivocada o dato alterado).") from None
    return plano.decode("utf-8")


def _leer_tabla(engine=None) -> dict[str, str]:
    import sqlalchemy as sa

    from . import db
    with (engine or db.motor()).connect() as conn:
        return {k: v for k, v in conn.execute(sa.select(db.secretos.c.clave, db.secretos.c.valor))}


def cargar_secretos_en_entorno(engine=None, pisar: bool = False) -> list[str]:
    """Descifra IOL_USERNAME, IOL_PASSWORD, TELEGRAM_TOKEN y TELEGRAM_CHAT_ID de la base y los pone en
    os.environ de este proceso. Devuelve los NOMBRES cargados. Una variable ya definida en el entorno no se
    pisa (salvo `pisar`): en la PC del dueño manda su .env. Sin DATABASE_URL no hace nada."""
    from . import db
    if engine is None and not db.hay_db():
        return []
    filas = _leer_tabla(engine)
    pendientes = [n for n in SECRETOS_ENTORNO if filas.get(n) and (pisar or not os.getenv(n))]
    if not pendientes:
        return []
    clave = clave_de_entorno()
    cargados = []
    for nombre in pendientes:
        try:
            os.environ[nombre] = descifrar(filas[nombre], clave)
            cargados.append(nombre)
        except SecretoIlegible as e:
            log.warning("Secreto %s ilegible: %s", nombre, e)   # solo el nombre, nunca el valor
    return cargados
