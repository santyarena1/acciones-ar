"""Cliente de la API v2 de InvertirOnline (IOL) y adaptador Broker.

Endpoints según la doc pública (https://api.invertironline.com). Los campos de respuesta se parsean de
forma defensiva: si IOL cambia nombres, ajustar acá y en tests/test_iol_parsers.py.
Nunca loguear el token ni la contraseña.
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime

import pandas as pd
import requests

from .base import Broker

BASE_URL = "https://api.invertironline.com"


class IOLError(Exception):
    pass


class IOLClient:
    def __init__(self, username: str | None = None, password: str | None = None, timeout: int = 20):
        self.username = username or os.getenv("IOL_USERNAME")
        self.password = password or os.getenv("IOL_PASSWORD")
        if not self.username or not self.password:
            raise IOLError("Faltan IOL_USERNAME / IOL_PASSWORD (completá el .env).")
        self.timeout = timeout
        self._access: str | None = None
        self._refresh: str | None = None
        self._expira = 0.0
        self.session = requests.Session()

    # --- autenticación ---------------------------------------------------
    def _pedir_token(self, data: dict) -> None:
        r = self.session.post(f"{BASE_URL}/token", data=data, timeout=self.timeout)
        if r.status_code != 200:
            raise IOLError(f"Login IOL falló (HTTP {r.status_code}). Revisá usuario/clave y que la API esté habilitada.")
        j = r.json()
        self._access = j["access_token"]
        self._refresh = j.get("refresh_token")
        self._expira = time.time() + int(j.get("expires_in", 900)) - 60

    def _auth(self) -> None:
        if self._access and time.time() < self._expira:
            return
        if self._refresh:
            try:
                self._pedir_token({"grant_type": "refresh_token", "refresh_token": self._refresh})
                return
            except IOLError:
                self._refresh = None
        self._pedir_token({"grant_type": "password", "username": self.username, "password": self.password})

    def _req(self, method: str, path: str, **kw):
        for intento in range(2):
            self._auth()
            r = self.session.request(method, f"{BASE_URL}{path}",
                                     headers={"Authorization": f"Bearer {self._access}"},
                                     timeout=self.timeout, **kw)
            if r.status_code == 401 and intento == 0:
                self._access = None
                continue
            if not r.ok:
                raise IOLError(f"{method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
            return r.json() if r.content else None
        raise IOLError("No autorizado tras reintentar.")

    # --- market data -----------------------------------------------------
    def quote(self, simbolo: str, mercado: str = "bCBA") -> dict:
        return self._req("GET", f"/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion")

    def history(self, simbolo: str, desde: date, hasta: date | None = None, mercado: str = "bCBA",
                ajustada: bool = True) -> pd.DataFrame:
        hasta = hasta or date.today()
        modo = "ajustada" if ajustada else "sinAjustar"
        raw = self._req("GET", f"/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion/seriehistorica/"
                               f"{desde:%Y-%m-%d}/{hasta:%Y-%m-%d}/{modo}")
        return parse_history(raw)

    # --- cuenta ----------------------------------------------------------
    def portfolio(self) -> dict:
        return self._req("GET", "/api/v2/portafolio/argentina")

    def account_status(self) -> dict:
        return self._req("GET", "/api/v2/estadocuenta")

    # --- órdenes ---------------------------------------------------------
    def send_order(self, lado: str, simbolo: str, cantidad: int, precio: float, mercado: str = "bCBA",
                   plazo: str = "t1", tipo_orden: str = "precioLimite", validez: datetime | None = None) -> dict:
        if lado not in ("COMPRAR", "VENDER"):
            raise IOLError(f"Lado inválido: {lado}")
        validez = validez or datetime.now().replace(hour=17, minute=0, second=0, microsecond=0)
        payload = {
            "mercado": mercado, "simbolo": simbolo, "cantidad": int(cantidad), "precio": float(precio),
            "plazo": plazo, "validez": validez.strftime("%Y-%m-%dT%H:%M:%S"), "tipoOrden": tipo_orden,
        }
        endpoint = "/api/v2/operar/Comprar" if lado == "COMPRAR" else "/api/v2/operar/Vender"
        return self._req("POST", endpoint, json=payload)


# --- parsers (testeables sin red) ----------------------------------------
def parse_history(raw) -> pd.DataFrame:
    filas = []
    for it in raw or []:
        fecha = it.get("fechaHora") or it.get("fecha")
        cierre = it.get("ultimoPrecio", it.get("cierre"))
        if fecha is None or cierre is None:
            continue
        filas.append({
            "date": pd.to_datetime(str(fecha)[:10]),
            "close": float(cierre),
            "volume": float(it.get("volumenNominal", it.get("volumen", 0)) or 0),
        })
    if not filas:
        return pd.DataFrame(columns=["close", "volume"])
    df = pd.DataFrame(filas).groupby("date").last().sort_index()
    return df[df["close"] > 0]


def parse_positions(raw) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for a in (raw or {}).get("activos", []):
        titulo = a.get("titulo") or {}
        simbolo = titulo.get("simbolo") or a.get("simbolo")
        tipo = (titulo.get("tipo") or "").lower()
        if not simbolo or (tipo and "accion" not in tipo):
            continue
        out[simbolo] = {"cantidad": int(a.get("cantidad", 0)), "precio": float(a.get("ultimoPrecio", 0) or 0)}
    return out


def parse_cash_ars(raw) -> float:
    for c in (raw or {}).get("cuentas", []):
        if "peso" in str(c.get("moneda", "")).lower():
            return float(c.get("disponible", 0) or 0)
    return 0.0


class IOLBroker(Broker):
    nombre = "iol"

    def __init__(self, client: IOLClient, settings: dict):
        self.client = client
        self.ej = settings["ejecucion"]

    def get_positions(self) -> dict[str, dict]:
        return parse_positions(self.client.portfolio())

    def get_cash_ars(self) -> float:
        return parse_cash_ars(self.client.account_status())

    def place_order(self, ticker: str, lado: str, cantidad: int, precio_limite: float) -> dict:
        res = self.client.send_order(lado, ticker, cantidad, precio_limite, mercado=self.ej["mercado"],
                                     plazo=self.ej["plazo"], tipo_orden=self.ej["tipo_orden"])
        return {"estado": "enviada", "respuesta": res}
