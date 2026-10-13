"""Función de Vercel: un ciclo del operador. La llama el cron (cada hora en horario BYMA) y la web
("Revisar ahora"). Protegida con CRON_SECRET (Vercel lo manda solo en sus crons como Bearer)."""
import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ.setdefault("AAR_DATA_DIR", "/tmp/aar/data")          # en Vercel solo /tmp es escribible
os.environ.setdefault("AAR_REPORTS_DIR", "/tmp/aar/reports")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _autorizado(cabecera: str) -> bool:
    secreto = os.environ.get("CRON_SECRET", "")
    return bool(secreto) and hmac.compare_digest(cabecera or "", f"Bearer {secreto}")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._correr()

    def do_POST(self):
        self._correr()

    def _correr(self):
        if not _autorizado(self.headers.get("Authorization", "")):
            return self._json(401, {"ok": False})
        q = parse_qs(urlparse(self.path).query)
        try:
            from src.motor_vercel import ejecutar
            r = ejecutar(solo_analisis=q.get("solo_analisis") == ["1"], forzar=q.get("forzar") == ["1"])
            self._json(200, r)
        except Exception as e:  # noqa: BLE001 - nunca devolver detalles: pueden tener datos de la cuenta
            print(f"[error] {type(e).__name__}")
            self._json(500, {"ok": False, "error": type(e).__name__})

    def _json(self, codigo: int, cuerpo: dict):
        datos = json.dumps(cuerpo).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)
