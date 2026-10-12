"""Avisos del operador: Telegram si está configurado (TELEGRAM_TOKEN + TELEGRAM_CHAT_ID en .env), si no,
notificación de escritorio de Windows. Si nada funciona, no rompe: el evento igual queda en la bitácora.

El texto de Windows viaja por variables de entorno (no se arma código PowerShell con él): sin inyección.
"""
from __future__ import annotations

import os
import subprocess
import sys

import requests

PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$t = [Security.SecurityElement]::Escape($env:AAR_TITULO)
$m = [Security.SecurityElement]::Escape($env:AAR_TEXTO)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$m</text></binding></visual></toast>")
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show(
    [Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def telegram(titulo: str, texto: str) -> bool:
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": f"{titulo}\n{texto}"[:4000]}, timeout=15)
        return r.ok
    except requests.RequestException:  # el mensaje de la excepción incluye la URL con el token: no se loguea
        return False


def windows(titulo: str, texto: str) -> bool:
    if sys.platform != "win32":
        return False
    env = {**os.environ, "AAR_TITULO": titulo[:120], "AAR_TEXTO": texto[:400]}
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PS], env=env,
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def notificar(titulo: str, texto: str) -> bool:
    return telegram(titulo, texto) or windows(titulo, texto)
