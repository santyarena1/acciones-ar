"""Históricos de precios en ARS, CCL histórico y conversión a USD. Con caché diaria en data/cache/."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from ..config import CACHE_DIR

CCL_URL = "https://api.argentinadatos.com/v1/cotizaciones/dolares/contadoconliqui"


def _cache_path(nombre: str) -> Path:
    return CACHE_DIR / f"{nombre}.csv"


def _cache_fresca(p: Path) -> bool:
    return p.exists() and date.fromtimestamp(p.stat().st_mtime) == date.today()


def _leer_cache(p: Path) -> pd.DataFrame:
    return pd.read_csv(p, index_col=0, parse_dates=True)


def _guardar_cache(df: pd.DataFrame, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p)


def _yf_download(simbolo: str, desde: date, hasta: date | None) -> pd.DataFrame:
    import yfinance as yf  # import diferido: no hace falta para tests

    df = yf.download(simbolo, start=desde, end=hasta, auto_adjust=True, progress=False)
    if df.empty:
        return pd.DataFrame(columns=["close", "volume"])
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.rename(columns=str.lower)[["close", "volume"]]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.dropna(subset=["close"])


def load_history(ticker: str, desde: date, hasta: date | None = None, fuente: str = "yfinance",
                 iol_client=None) -> pd.DataFrame:
    """Precios en ARS (columnas close, volume)."""
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


def load_ccl(desde: date, hasta: date | None = None) -> pd.Series:
    """CCL diario. Fuente: argentinadatos.com; si falla, CCL implícito GGAL.BA / (GGAL ADR / 10)."""
    p = _cache_path("ccl")
    if _cache_fresca(p):
        s = _leer_cache(p).iloc[:, 0]
        return s[s.index >= pd.Timestamp(desde)]
    try:
        r = requests.get(CCL_URL, timeout=20)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        df["fecha"] = pd.to_datetime(df["fecha"])
        s = ((df["compra"].astype(float) + df["venta"].astype(float)) / 2).set_axis(df["fecha"]).sort_index()
        s = s[~s.index.duplicated(keep="last")]
    except Exception:
        local = _yf_download("GGAL.BA", desde - timedelta(days=10), hasta)["close"]
        adr = _yf_download("GGAL", desde - timedelta(days=10), hasta)["close"]
        s = (local / (adr / 10)).dropna()
    s.name = "ccl"
    if not s.empty:
        _guardar_cache(s.to_frame(), p)
    return s[s.index >= pd.Timestamp(desde)]


def to_usd(df_ars: pd.DataFrame, ccl: pd.Series) -> pd.DataFrame:
    """Divide close por el CCL del mismo día (forward-fill para feriados). Volumen queda en nominales."""
    ccl_al = ccl.reindex(df_ars.index.union(ccl.index)).sort_index().ffill().reindex(df_ars.index)
    out = df_ars.copy()
    out["close"] = df_ars["close"] / ccl_al
    return out.dropna(subset=["close"])
