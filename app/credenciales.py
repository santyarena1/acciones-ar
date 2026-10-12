"""Credenciales y conexiones guardadas en el archivo .env del proyecto (solo en tu PC; nunca se muestran).

En Vercel estas mismas claves van como variables de entorno del proyecto.
"""
from __future__ import annotations

import os

from dotenv import dotenv_values, set_key, unset_key

from src.config import ROOT

ENV = ROOT / ".env"
CLAVES_IOL = ("IOL_USERNAME", "IOL_PASSWORD")
CLAVES_TELEGRAM = ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")


def _valores() -> dict[str, str]:
    return {k: v for k, v in dotenv_values(ENV).items() if v} if ENV.exists() else {}


def configurado(*claves: str) -> bool:
    v = _valores()
    return all(v.get(k) or os.getenv(k) for k in claves)


def usuario_iol() -> str:
    return _valores().get("IOL_USERNAME", "")


def guardar(**pares: str) -> None:
    """Guarda en .env y en el proceso actual. Valores vacíos no pisan lo que había."""
    ENV.touch(exist_ok=True)
    for k, v in pares.items():
        if v:
            set_key(str(ENV), k, v, quote_mode="always")
            os.environ[k] = v


def borrar(*claves: str) -> None:
    if not ENV.exists():
        return
    for k in claves:
        unset_key(str(ENV), k)
        os.environ.pop(k, None)


def modo_real_habilitado() -> bool:
    return (_valores().get("IOL_LIVE_TRADING") or os.getenv("IOL_LIVE_TRADING")) == "1"


def habilitar_modo_real(si: bool) -> None:
    ENV.touch(exist_ok=True)
    set_key(str(ENV), "IOL_LIVE_TRADING", "1" if si else "0", quote_mode="never")
    os.environ["IOL_LIVE_TRADING"] = "1" if si else "0"


def probar_iol(usuario: str, clave: str) -> tuple[bool, str]:
    """Login + lectura de cuenta (no opera). Devuelve (ok, mensaje legible)."""
    from src.broker.iol import IOLBroker, IOLClient
    from src.config import load_settings

    try:
        b = IOLBroker(IOLClient(usuario, clave), load_settings())
        caja, pos = b.get_cash_ars(), b.get_positions()
        return True, f"Conectado. Tenés ${caja:,.0f} disponibles y {len(pos)} activos en cartera.".replace(",", ".")
    except Exception as e:  # el mensaje de IOLError ya viene sin datos sensibles
        return False, f"No se pudo conectar: {e}"


def probar_telegram(token: str, chat_id: str) -> tuple[bool, str]:
    import requests

    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": "Panel de inversión: conexión con Telegram OK."}, timeout=15)
        return (True, "Te mandé un mensaje de prueba.") if r.ok else (False, f"Telegram respondió {r.status_code}.")
    except Exception as e:
        return False, f"No se pudo conectar con Telegram: {type(e).__name__}"


def buscar_chat_id(token: str) -> str | None:
    """Después de que le escribas al bot, encuentra tu chat (el último que le habló)."""
    import requests

    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json()
        chats = [u["message"]["chat"]["id"] for u in r.get("result", []) if "message" in u]
        return str(chats[-1]) if chats else None
    except Exception:
        return None
