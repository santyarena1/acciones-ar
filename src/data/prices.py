"""Históricos de precios, CCL, dólar oficial y conversión a USD. Con caché diaria en data/cache/.

Convenciones de salida (DataFrames con índice de fechas):
- ARS (BYMA): columnas close, volume (volume en nominales).
- USD: columna close; para acciones locales = ARS / CCL; para CEDEARs = precio del subyacente en USD.
"""
from __future__ import annotations

import math
import time
from datetime import date, datetime
from datetime import time as dtime
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from ..config import CACHE_DIR

AD_URL = "https://api.argentinadatos.com/v1"
CCL_URL = f"{AD_URL}/cotizaciones/dolares/contadoconliqui"
OFICIAL_URL = f"{AD_URL}/cotizaciones/dolares/oficial"
RIESGO_PAIS_URL = f"{AD_URL}/finanzas/indices/riesgo-pais"
VACIO = pd.DataFrame(columns=["close", "volume"])
HOLGURA_HISTORIA_DIAS = 10   # una caché que arranca más tarde que esto respecto de `desde` se vuelve a bajar
MIN_RUEDAS_VOLUMEN = 10      # con menos ruedas no se puede afirmar que un activo es líquido


def _cache_path(nombre: str) -> Path:
    return CACHE_DIR / f"{nombre.replace('^', '_')}.csv"


def _cache_fresca(p: Path, ttl_min: float | None = None) -> bool:
    """Sin TTL: vale el día. Con TTL (minutos): además tiene que ser más nueva que eso (corridas intradiarias)."""
    if not p.exists():
        return False
    mtime = p.stat().st_mtime
    if date.fromtimestamp(mtime) != date.today():
        return False
    return ttl_min is None or (time.time() - mtime) <= ttl_min * 60


def _leer_cache(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, index_col=0, parse_dates=True)


def _guardar_cache(df: pd.DataFrame, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p)


def _normalizar_yf(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return VACIO.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)
    if "close" not in df.columns:   # símbolo que falló dentro de un lote: vacío, no rompe la corrida
        return VACIO.copy()
    cols = [c for c in ("close", "volume") if c in df.columns]
    df = df[cols].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.dropna(subset=["close"])


def _yf_download(simbolo: str, desde: date, hasta: date | None) -> pd.DataFrame:
    import yfinance as yf  # import diferido: no hace falta para tests

    return _normalizar_yf(yf.download(simbolo, start=desde, end=hasta, auto_adjust=True, progress=False))


def _yf_lote(simbolos: list[str], desde: date) -> dict[str, pd.DataFrame]:
    """Descarga varios símbolos de una sola vez (mucho más rápido que de a uno)."""
    import yfinance as yf

    if not simbolos:
        return {}
    raw = yf.download(simbolos, start=desde, auto_adjust=True, progress=False, group_by="ticker", threads=True)
    out = {}
    for s in simbolos:
        try:
            sub = raw[s] if len(simbolos) > 1 else raw
        except KeyError:
            continue
        df = _normalizar_yf(sub.copy())
        if not df.empty:
            out[s] = df
    return out


def _cache_cubre(df: pd.DataFrame, desde: date) -> bool:
    """La caché sirve solo si arranca cerca de `desde` (si no, el backtest correría con historia truncada)."""
    return not df.empty and df.index[0] <= pd.Timestamp(desde) + pd.Timedelta(days=HOLGURA_HISTORIA_DIAS)


def load_many(simbolos: list[str], desde: date, ttl_min: float | None = None) -> dict[str, pd.DataFrame]:
    """Históricos de yfinance con caché por símbolo (diaria o con TTL). Devuelve solo los que tienen datos.
    Si la descarga falla, se usa la caché anterior (lo viejo lo marca después `diagnostico_calidad`)."""
    out, faltan, respaldo = {}, [], {}
    for s in simbolos:
        p = _cache_path(f"yf_{s}")
        df = _leer_cache(p) if p.exists() else None
        if df is not None and _cache_fresca(p, ttl_min) and _cache_cubre(df, desde):
            out[s] = df[df.index >= pd.Timestamp(desde)]
            continue
        faltan.append(s)
        if df is not None and not df.empty:
            respaldo[s] = df
    for i in range(0, len(faltan), 40):
        for s, df in _yf_lote(faltan[i:i + 40], desde).items():
            _guardar_cache(df, _cache_path(f"yf_{s}"))
            out[s] = df
    for s, df in respaldo.items():
        if s not in out:
            print(f"  [aviso] no pude actualizar {s}: uso la caché anterior")
            out[s] = df[df.index >= pd.Timestamp(desde)]
    return out


def load_history(ticker: str, desde: date, hasta: date | None = None, fuente: str = "yfinance",
                 iol_client=None) -> pd.DataFrame:
    """Precios en ARS de BYMA (columnas close, volume)."""
    p = _cache_path(f"{fuente}_{ticker}")
    if _cache_fresca(p):
        df = _leer_cache(p)
        return df[df.index >= pd.Timestamp(desde)]
    if fuente == "iol":
        if iol_client is None:
            raise ValueError("fuente=iol requiere iol_client")
        df = iol_client.history(ticker, desde, hasta)
    else:
        df = _yf_download(f"{ticker}.BA", desde, hasta)
    if not df.empty:
        _guardar_cache(df, p)
    return df


def _serie_argentinadatos(url: str, nombre: str, desde: date, campo: str | None = None,
                          ttl_min: float | None = None) -> pd.Series:
    p = _cache_path(nombre)
    if _cache_fresca(p, ttl_min):
        s = _leer_cache(p).iloc[:, 0]
        return s[s.index >= pd.Timestamp(desde)]
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["fecha"] = pd.to_datetime(df["fecha"])
    if campo:
        valores = df[campo].astype(float)
    else:
        valores = (df["compra"].astype(float) + df["venta"].astype(float)) / 2
    s = valores.set_axis(df["fecha"]).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    s.name = nombre
    _guardar_cache(s.to_frame(), p)
    return s[s.index >= pd.Timestamp(desde)]


def load_ccl(desde: date, hasta: date | None = None, ttl_min: float | None = None) -> pd.Series:
    """CCL diario. Fuente: argentinadatos.com; si falla, CCL implícito GGAL.BA / (GGAL ADR / 10)."""
    try:
        return _serie_argentinadatos(CCL_URL, "ccl", desde, ttl_min=ttl_min)
    except Exception as e:
        print(f"  [aviso] CCL de argentinadatos no disponible ({e}); uso CCL implícito de GGAL")
    local = _yf_download("GGAL.BA", desde - timedelta(days=10), hasta)["close"]
    adr = _yf_download("GGAL", desde - timedelta(days=10), hasta)["close"]
    s = (local / (adr / 10)).dropna()
    s.name = "ccl"
    return s[s.index >= pd.Timestamp(desde)]


def load_oficial(desde: date) -> pd.Series:
    return _serie_argentinadatos(OFICIAL_URL, "oficial", desde)


def load_riesgo_pais(desde: date) -> pd.Series:
    return _serie_argentinadatos(RIESGO_PAIS_URL, "riesgo_pais", desde, campo="valor")


def to_usd(df_ars: pd.DataFrame, ccl: pd.Series) -> pd.DataFrame:
    """Divide close por el CCL del mismo día (forward-fill para feriados). Volumen queda en nominales."""
    ccl_al = ccl.reindex(df_ars.index.union(ccl.index)).sort_index().ffill().reindex(df_ars.index)
    out = df_ars.copy()
    out["close"] = df_ars["close"] / ccl_al
    return out.dropna(subset=["close"])


def volumen_ars_promedio(df_ars: pd.DataFrame, ruedas: int = 20) -> float | None:
    """Monto operado promedio en pesos de las últimas `ruedas` (precio x nominales)."""
    if df_ars is None or len(df_ars) < MIN_RUEDAS_VOLUMEN or "volume" not in df_ars.columns:
        return None
    monto = (df_ars["close"] * df_ars["volume"]).tail(ruedas)
    return float(monto.mean()) if len(monto) else None


# --- calidad de datos -------------------------------------------------------------------------------

def limpiar_picos(df: pd.DataFrame, umbral: float) -> pd.DataFrame:
    """Saca prints aislados: una rueda que se mueve más de `umbral` (log) y al día siguiente vuelve.
    Ej. CELU 18/02/2026: 304 -> 184 -> 276. Una caída que se sostiene es real y se conserva."""
    if df is None or len(df) < 3:
        return df
    r = np.log(df["close"].astype(float)).diff()
    sig = r.shift(-1)
    pico = (r.abs() > umbral) & (sig.abs() > umbral) & (np.sign(r) != np.sign(sig)) & ((r + sig).abs() < umbral / 2)
    return df[~pico.fillna(False)]


def ruedas_cerradas(df: pd.DataFrame, ahora: datetime, hora_cierre: dtime) -> pd.DataFrame:
    """Durante la rueda yfinance trae la vela de hoy incompleta. Para los indicadores se usa solo lo cerrado,
    así la señal no cambia de 15 en 15 minutos (el precio en vivo se sigue usando para las órdenes)."""
    if df is None or df.empty or ahora.time() >= hora_cierre:
        return df
    return df[df.index.normalize() < pd.Timestamp(ahora.date())]


def diagnostico_calidad(df_ars: pd.DataFrame | None, hoy: date, cfg: dict) -> str:
    """'' si el precio es usable para operar; si no, el motivo. Mira la serie en ARS de BYMA."""
    if df_ars is None or df_ars.empty:
        return "sin precio en BYMA"
    ultimo = float(df_ars["close"].iloc[-1])
    if not math.isfinite(ultimo) or ultimo <= 0:
        return "último precio inválido"
    dias = int(np.busday_count(df_ars.index[-1].date(), hoy))
    if dias > cfg.get("max_dias_sin_precio", 3):
        return f"sin precio hace {dias} ruedas"
    if len(df_ars) >= 2:
        salto = math.log(ultimo / float(df_ars["close"].iloc[-2]))
        if abs(salto) > cfg.get("max_salto_diario", 0.25):
            return f"salto de {math.expm1(salto):+.0%} en la última rueda (no se persigue ni se vende por un dato suelto)"
    n = int(cfg.get("ruedas_sin_volumen_max", 3))
    if "volume" in df_ars.columns and len(df_ars) > n and (df_ars["volume"].tail(n + 1).fillna(0) <= 0).all():
        return f"sin operaciones en las últimas {n + 1} ruedas"
    return ""


def desvio_ratio_cedear(ars: pd.Series, usd: pd.Series, ccl: pd.Series, ventana: int = 20) -> float | None:
    """CCL implícito del CEDEAR vs. su propia historia: ratio_t = CCL_t * subyacente_t / CEDEAR_t.
    El ratio de conversión es constante, así que si el último se aleja de la mediana reciente, el precio del
    CEDEAR en BYMA está viejo/roto (o cambió el ratio). Devuelve el desvío relativo, o None si no hay datos."""
    ccl_al = ccl.reindex(ccl.index.union(ars.index)).sort_index().ffill()
    j = pd.concat([ars, usd, ccl_al], axis=1, join="inner").dropna()
    if len(j) < 6:
        return None
    ratio = j.iloc[:, 2] * j.iloc[:, 1] / j.iloc[:, 0]
    ref = ratio.iloc[-ventana - 1:-1].median()
    return float(ratio.iloc[-1] / ref - 1) if ref and math.isfinite(ref) else None
