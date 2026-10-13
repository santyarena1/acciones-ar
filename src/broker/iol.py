"""Cliente de la API v2 de InvertirOnline (IOL) y adaptador Broker.

Endpoints y nombres de campos verificados contra el swagger v2 de IOL (copia pública del
2026-09) y clientes open source. Los campos de respuesta se parsean de forma defensiva: si IOL
cambia nombres, ajustar acá y en tests/test_iol_parsers.py (fixtures en tests/fixtures/iol_*.json).

Seguridad: nunca loguear ni meter en excepciones el token, el refresh token ni la contraseña.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from datetime import date, datetime, time as dtime, timedelta, timezone
from typing import Any

import pandas as pd
import requests

from .base import Broker
from .iol_parsers import (  # noqa: F401  (re-exportados: la API pública sigue siendo src.broker.iol)
    MULT_PRECIO,
    PLAZO_A_LIQUIDACION,
    clasificar_tipo,
    multiplicador_precio,
    parse_cash_ars,
    parse_history,
    parse_operaciones,
    parse_order_response,
    parse_panel,
    parse_positions,
    parse_quote,
)

BASE_URL = "https://api.invertironline.com"

# Reintentos: 429 (rate limit) y errores 5xx / de conexión.
ESTADOS_REINTENTABLES = frozenset({429, 500, 502, 503, 504})
MAX_REINTENTOS = 3
BACKOFF_BASE_SEG = 1.0
BACKOFF_MAX_SEG = 30.0
INTERVALO_MIN_SEG = 0.25  # rate limiter simple entre requests

# Cierre de BYMA (hora Argentina). Argentina no tiene horario de verano: UTC-3 fijo como fallback.
HORA_CIERRE_BYMA = dtime(17, 0)
_TZ_NOMBRE = "America/Argentina/Buenos_Aires"

_PLAZO_A_LIQUIDACION = PLAZO_A_LIQUIDACION

_LADOS = {"COMPRAR": "/api/v2/operar/Comprar", "VENDER": "/api/v2/operar/Vender"}
_ESTADOS_FILTRO = ("todas", "pendientes", "terminadas", "canceladas")


class IOLError(Exception):
    pass


class IOLOrdenIncierta(IOLError):
    """La orden pudo haber entrado (timeout, corte de red, 5xx o respuesta ilegible): NO reenviar sin revisar."""


def tz_argentina():
    """Zona horaria de Buenos Aires (zoneinfo); si no hay base tz (Windows sin tzdata), UTC-3 fijo."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(_TZ_NOMBRE)
    except Exception:  # ZoneInfoNotFoundError / ImportError: Argentina es UTC-3 todo el año
        return timezone(timedelta(hours=-3), "ART")


def validez_cierre_mercado(ahora: datetime | None = None, feriados: Iterable[date] = (),
                           cierre: dtime = HORA_CIERRE_BYMA) -> datetime:
    """Validez de una orden: hoy al cierre de BYMA (hora Argentina).

    Si ya pasó el cierre, o hoy es fin de semana/feriado, devuelve el cierre del próximo día hábil.
    Devuelve un datetime *naive* en hora Argentina (así lo espera el campo `validez` de IOL).
    """
    tz = tz_argentina()
    if ahora is None:
        ahora_ar = datetime.now(tz)
    elif ahora.tzinfo is None:
        ahora_ar = ahora  # se asume que ya viene en hora Argentina
    else:
        ahora_ar = ahora.astimezone(tz)
    no_habiles = set(feriados)

    def es_habil(d: date) -> bool:
        return d.weekday() < 5 and d not in no_habiles

    dia = ahora_ar.date()
    if not es_habil(dia) or ahora_ar.time() >= cierre:
        dia += timedelta(days=1)
        while not es_habil(dia):
            dia += timedelta(days=1)
    return datetime.combine(dia, cierre)


class _RateLimiter:
    """Garantiza un intervalo mínimo entre requests consecutivos."""

    def __init__(self, intervalo_min: float, reloj: Callable[[], float], dormir: Callable[[float], None]):
        self.intervalo_min = max(0.0, float(intervalo_min))
        self._reloj = reloj
        self._dormir = dormir
        self._ultimo: float | None = None

    def esperar(self) -> None:
        if self._ultimo is not None and self.intervalo_min > 0:
            falta = self.intervalo_min - (self._reloj() - self._ultimo)
            if falta > 0:
                self._dormir(falta)
        self._ultimo = self._reloj()


class IOLClient:
    """Cliente HTTP de IOL con token+refresh, reintentos con backoff exponencial y rate limit.

    Los POST de órdenes NO se reintentan ante 5xx/timeouts (la orden pudo haber entrado y se
    duplicaría): solo ante 429 o si la conexión ni siquiera se estableció.
    """

    def __init__(self, username: str | None = None, password: str | None = None, timeout: int = 20,
                 *, session: requests.Session | None = None, max_reintentos: int = MAX_REINTENTOS,
                 backoff_base: float = BACKOFF_BASE_SEG, intervalo_min: float = INTERVALO_MIN_SEG,
                 dormir: Callable[[float], None] = time.sleep,
                 reloj: Callable[[], float] = time.monotonic):
        self.username = username or os.getenv("IOL_USERNAME")
        self.password = password or os.getenv("IOL_PASSWORD")
        if not self.username or not self.password:
            raise IOLError("Faltan IOL_USERNAME / IOL_PASSWORD (completá el .env).")
        self.timeout = timeout
        self.max_reintentos = max(0, int(max_reintentos))
        self.backoff_base = max(0.0, float(backoff_base))
        self._dormir = dormir
        self._limiter = _RateLimiter(intervalo_min, reloj, dormir)
        self._access: str | None = None
        self._refresh: str | None = None
        self._expira = 0.0
        self.session = session or requests.Session()

    def __repr__(self) -> str:  # nunca exponer credenciales ni token
        return f"IOLClient(usuario={'***' if self.username else None}, autenticado={self._access is not None})"

    # --- seguridad -------------------------------------------------------
    def _censurar(self, texto: str) -> str:
        """Saca cualquier secreto que pudiera aparecer en un texto (por las dudas)."""
        for secreto in (self._access, self._refresh, self.password):
            if secreto:
                texto = texto.replace(secreto, "***")
        return texto

    # --- transporte con reintentos ----------------------------------------
    def _espera_backoff(self, intento: int, resp: requests.Response | None) -> float:
        if resp is not None:
            retry_after = resp.headers.get("Retry-After") if resp.headers else None
            if retry_after:
                try:
                    return min(BACKOFF_MAX_SEG, max(0.0, float(retry_after)))
                except ValueError:
                    pass
        return min(BACKOFF_MAX_SEG, self.backoff_base * (2 ** intento))

    def _enviar(self, method: str, url: str, *, idempotente: bool = True, **kw) -> requests.Response:
        """Hace el request con rate limit y reintentos. No conoce de autenticación."""
        ultimo_error = ""
        for intento in range(self.max_reintentos + 1):
            self._limiter.esperar()
            try:
                r = self.session.request(method, url, timeout=self.timeout, **kw)
            except requests.exceptions.ConnectTimeout:
                ultimo_error = "timeout de conexión"  # no llegó a enviarse: seguro reintentar
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                ultimo_error = f"error de red ({type(e).__name__})"
                if not idempotente:
                    raise IOLOrdenIncierta(f"{method} {self._ruta(url)}: {ultimo_error}. La orden PUDO haber "
                                   "entrado: revisá las operaciones en IOL antes de reenviar.") from None
            else:
                if r.status_code not in ESTADOS_REINTENTABLES:
                    return r
                ultimo_error = f"HTTP {r.status_code}"
                if not idempotente and r.status_code != 429:
                    return r  # 5xx en una orden: no reintentar, que lo maneje el llamador
                if intento < self.max_reintentos:
                    self._dormir(self._espera_backoff(intento, r))
                continue
            if intento < self.max_reintentos:
                self._dormir(self._espera_backoff(intento, None))
        raise IOLError(f"{method} {self._ruta(url)}: falló tras {self.max_reintentos + 1} intentos "
                       f"({ultimo_error}).")

    @staticmethod
    def _ruta(url: str) -> str:
        return url.replace(BASE_URL, "")

    # --- autenticación ---------------------------------------------------
    def _pedir_token(self, data: dict) -> None:
        r = self._enviar("POST", f"{BASE_URL}/token", data=data)
        if r.status_code != 200:
            # No incluir el body: podría reflejar datos del form.
            raise IOLError(f"Login IOL falló (HTTP {r.status_code}). Revisá usuario/clave y que la API "
                           "esté habilitada en tu cuenta.")
        try:
            j = r.json()
            self._access = j["access_token"]
        except (ValueError, KeyError, TypeError):
            raise IOLError("Login IOL: respuesta sin access_token.") from None
        self._refresh = j.get("refresh_token")
        try:
            expira_en = int(j.get("expires_in", 900))
        except (TypeError, ValueError):
            expira_en = 900
        self._expira = time.time() + expira_en - 60

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

    def _req(self, method: str, path: str, *, idempotente: bool = True, **kw) -> Any:
        for intento in range(2):
            self._auth()
            r = self._enviar(method, f"{BASE_URL}{path}", idempotente=idempotente,
                             headers={"Authorization": f"Bearer {self._access}"}, **kw)
            if r.status_code == 401 and intento == 0:
                self._access = None
                self._expira = 0.0
                continue
            if not r.ok:
                cuerpo = self._censurar((r.text or "")[:300])
                aviso = (" La orden PUDO haber entrado: revisá las operaciones en IOL antes de reenviar."
                         if not idempotente and r.status_code >= 500 else "")
                error = IOLOrdenIncierta if aviso else IOLError
                raise error(f"{method} {path} -> HTTP {r.status_code}: {cuerpo}{aviso}")
            if not r.content:
                return None
            try:
                return r.json()
            except ValueError:
                error = IOLError if idempotente else IOLOrdenIncierta
                raise error(f"{method} {path}: la respuesta no es JSON.") from None
        raise IOLError("No autorizado tras reintentar (token rechazado).")

    # --- market data -----------------------------------------------------
    def quote(self, simbolo: str, mercado: str = "bCBA", plazo: str | None = None) -> dict:
        params = {"model.plazo": plazo} if plazo else None
        return self._req("GET", f"/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion", params=params)

    def history(self, simbolo: str, desde: date, hasta: date | None = None, mercado: str = "bCBA",
                ajustada: bool = True) -> pd.DataFrame:
        hasta = hasta or date.today()
        modo = "ajustada" if ajustada else "sinAjustar"
        raw = self._req("GET", f"/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion/seriehistorica/"
                               f"{desde:%Y-%m-%d}/{hasta:%Y-%m-%d}/{modo}")
        return parse_history(raw)

    def panel(self, instrumento: str = "acciones", panel: str = "Merval", pais: str = "argentina") -> Any:
        """Cotizaciones de un panel. Ej.: ('acciones','Merval'), ('acciones','Panel General').

        Ojo: el swagger no acepta 'cedears' como instrumento de panel; para CEDEARs usar
        `cotizaciones_todos('cedears')`. Para ver los paneles válidos: `paneles('acciones')`.
        """
        return self._req("GET", f"/api/v2/Cotizaciones/{instrumento}/{panel}/{pais}")

    def cotizaciones_todos(self, instrumento: str = "cedears", pais: str = "argentina") -> Any:
        """Todas las cotizaciones de un instrumento (acciones, cedears, ...)."""
        return self._req("GET", f"/api/v2/Cotizaciones/{instrumento}/{pais}/Todos")

    def paneles(self, instrumento: str = "acciones", pais: str = "argentina") -> Any:
        """Lista de paneles disponibles para un instrumento."""
        return self._req("GET", f"/api/v2/{pais}/Titulos/Cotizacion/Paneles/{instrumento}")

    # --- cuenta ----------------------------------------------------------
    def portfolio(self, pais: str = "argentina") -> dict:
        return self._req("GET", f"/api/v2/portafolio/{pais}")

    def account_status(self) -> dict:
        return self._req("GET", "/api/v2/estadocuenta")

    # --- operaciones -----------------------------------------------------
    def operaciones(self, estado: str | None = None, desde: date | None = None, hasta: date | None = None,
                    pais: str | None = "argentina", numero: int | None = None) -> list:
        if estado is not None and estado not in _ESTADOS_FILTRO:
            raise IOLError(f"Estado de filtro inválido: {estado} (usá {', '.join(_ESTADOS_FILTRO)}).")
        params: dict[str, Any] = {}
        if estado:
            params["filtro.estado"] = estado
        if desde:
            params["filtro.fechaDesde"] = f"{desde:%Y-%m-%d}"
        if hasta:
            params["filtro.fechaHasta"] = f"{hasta:%Y-%m-%d}"
        if pais:
            params["filtro.pais"] = pais
        if numero is not None:
            params["filtro.numero"] = int(numero)
        return self._req("GET", "/api/v2/operaciones", params=params) or []

    def operacion(self, numero: int | str) -> dict:
        return self._req("GET", f"/api/v2/operaciones/{_numero_valido(numero)}")

    def cancelar(self, numero: int | str) -> dict:
        return self._req("DELETE", f"/api/v2/operaciones/{_numero_valido(numero)}")

    def send_order(self, lado: str, simbolo: str, cantidad: int, precio: float, mercado: str = "bCBA",
                   plazo: str = "t1", tipo_orden: str = "precioLimite", validez: datetime | None = None,
                   feriados: Iterable[date] = ()) -> dict:
        if lado not in _LADOS:
            raise IOLError(f"Lado inválido: {lado} (usá COMPRAR o VENDER).")
        if int(cantidad) <= 0 or float(precio) <= 0:
            raise IOLError("Cantidad y precio tienen que ser mayores a cero.")
        if plazo not in _PLAZO_A_LIQUIDACION:
            raise IOLError(f"Plazo inválido: {plazo} (usá t0, t1, t2 o t3).")
        validez = validez or validez_cierre_mercado(feriados=feriados)
        payload = {
            "mercado": mercado, "simbolo": simbolo, "cantidad": int(cantidad), "precio": float(precio),
            "plazo": plazo, "validez": validez.strftime("%Y-%m-%dT%H:%M:%S"), "tipoOrden": tipo_orden,
        }
        return self._req("POST", _LADOS[lado], json=payload, idempotente=False)


def _numero_valido(numero: int | str) -> int:
    try:
        n = int(numero)
    except (TypeError, ValueError):
        raise IOLError(f"Número de operación inválido: {numero!r}") from None
    if n <= 0:
        raise IOLError(f"Número de operación inválido: {numero!r}")
    return n


class IOLBroker(Broker):
    nombre = "iol"

    def __init__(self, client: IOLClient, settings: dict):
        self.client = client
        ej = (settings or {}).get("ejecucion", {}) or {}
        self.mercado: str = ej.get("mercado", "bCBA")
        self.plazo: str = ej.get("plazo", "t1")
        self.tipo_orden: str = ej.get("tipo_orden", "precioLimite")
        self.feriados: list[date] = [date.fromisoformat(str(d)) for d in ej.get("feriados", []) or []]

    def get_positions(self) -> dict[str, dict]:
        return parse_positions(self.client.portfolio())

    def get_cash_ars(self) -> float:
        return parse_cash_ars(self.client.account_status(), plazo=self.plazo)

    def diagnostico(self) -> dict:
        """Cómo informa IOL los saldos y la cartera (para verificar la lectura; va a la base privada)."""
        from .iol_parsers import resumen_estadocuenta, resumen_portafolio
        return {"estadocuenta": resumen_estadocuenta(self.client.account_status()),
                "portafolio": resumen_portafolio(self.client.portfolio()), "plazo": self.plazo}

    def get_quote(self, ticker: str) -> dict | None:
        return parse_quote(self.client.quote(ticker, mercado=self.mercado))

    def open_orders(self) -> list[dict]:
        return parse_operaciones(self.client.operaciones(estado="pendientes"))

    def cancel_order(self, order_id: str | int) -> dict:
        res = parse_order_response(self.client.cancelar(order_id))
        estado = "cancelada" if res["estado"] == "enviada" else res["estado"]
        return {"estado": estado, "id": res["id"] if res["id"] is not None else order_id,
                "mensaje": res["mensaje"]}

    def place_order(self, ticker: str, lado: str, cantidad: int, precio_limite: float,
                    mult: float = 1.0) -> dict:
        """Nunca lanza por errores de IOL: devuelve estado 'enviada' | 'rechazada' | 'incierta' | 'desconocido'.

        'incierta' = la orden PUDO haber entrado: el llamador no tiene que reenviarla en el día (ver
        Bitacora.ordenes_del_dia). `mult` no se usa: IOL recibe el precio tal cual se cotiza (renta fija: cada
        100 VN) y la cantidad en VN."""
        try:
            res = self.client.send_order(lado, ticker, cantidad, precio_limite, mercado=self.mercado,
                                         plazo=self.plazo, tipo_orden=self.tipo_orden, feriados=self.feriados)
        except IOLOrdenIncierta as e:
            return {"estado": "incierta", "id": None, "mensaje": str(e)}
        except IOLError as e:  # validación, login o 4xx: la orden no entró
            return {"estado": "rechazada", "id": None, "mensaje": str(e)}
        return parse_order_response(res)
