"""Métricas fundamentales por ticker.

Fuentes, en orden de prioridad:
1. data/fundamentals_manual.csv  (lo que cargues a mano desde balances CNV / reportes; pisa todo)
2. yfinance: acciones locales con el ticker de BYMA ("ALUA.BA": balance y precio en ARS, consistente);
   CEDEARs con el subyacente en USD.

No se usa el ADR para ratios: yfinance mezcla estados en ARS con precio en USD (ej. P/B de GGAL 9,7 vs 1,0).
Ojo: el crecimiento de ventas de las locales es nominal en pesos (incluye inflación); el score relativo
dentro del grupo de acciones locales lo compensa, el absoluto no.
Caché diaria en data/cache/fundamentales.json (bajar ~100 `.info` tarda).
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd

from ..config import CACHE_DIR, ROOT

METRICAS = ["pe", "ev_ebitda", "pb", "roe", "operating_margin", "net_debt_ebitda", "revenue_growth", "fcf_yield"]
CACHE = CACHE_DIR / "fundamentales.json"
# Rangos plausibles: fuera de esto el dato de yfinance es basura (monedas mezcladas, divisiones por casi cero).
# Ej. reales: PAMP.BA EV/EBITDA 7332 (EV en ARS / EBITDA en USD), BRK-B P/B 0,001, CECO2.BA ventas +718%.
LIMITES = {"pe": (-1e9, 300.0), "ev_ebitda": (-1e9, 150.0), "pb": (0.05, 100.0), "roe": (-3.0, 5.0),
           "operating_margin": (-3.0, 1.0), "net_debt_ebitda": (-30.0, 40.0), "revenue_growth": (-0.9, 3.0),
           "fcf_yield": (-1.0, 1.0)}
# Si el balance está en otra moneda que la cotización, estos ratios de yfinance mezclan monedas
RATIOS_DE_PRECIO = ("ev_ebitda", "pb", "fcf_yield")


def _num(x):
    try:
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else v
    except (TypeError, ValueError):
        return None


def from_yf_info(info: dict) -> dict:
    """Mapea el dict `Ticker.info` de yfinance a nuestras métricas."""
    m = {
        "pe": _num(info.get("trailingPE")),
        "ev_ebitda": _num(info.get("enterpriseToEbitda")),
        "pb": _num(info.get("priceToBook")),
        "roe": _num(info.get("returnOnEquity")),
        "operating_margin": _num(info.get("operatingMargins")),
        "revenue_growth": _num(info.get("revenueGrowth")),
    }
    fcf, mcap = _num(info.get("freeCashflow")), _num(info.get("marketCap"))
    m["fcf_yield"] = fcf / mcap if fcf is not None and mcap else None
    deuda, caja, ebitda = _num(info.get("totalDebt")), _num(info.get("totalCash")), _num(info.get("ebitda"))
    if deuda is not None and ebitda and ebitda > 0:
        m["net_debt_ebitda"] = (deuda - (caja or 0.0)) / ebitda
    else:
        m["net_debt_ebitda"] = None
    mon, mon_bal = info.get("currency"), info.get("financialCurrency")
    if mon and mon_bal and str(mon).upper() != str(mon_bal).upper():
        m.update(dict.fromkeys(RATIOS_DE_PRECIO))
    if m["pe"] is None and (_num(info.get("trailingEps")) or 0) < 0:
        m["pe"] = -1.0  # yfinance no da P/E con pérdidas: se marca como pérdida, no como dato faltante
    return m


def sanear(m: dict, limites: dict | None = None) -> dict:
    """Descarta valores fuera de rango plausible. Un P/E faltante con ROE negativo cuenta como pérdida."""
    lim = limites or LIMITES
    out = {}
    for k, v in m.items():
        bajo, alto = (float(x) for x in lim.get(k, (-math.inf, math.inf)))
        out[k] = v if v is not None and bajo <= v <= alto else None
    if out.get("pe") is None and out.get("roe") is not None and out["roe"] < 0:
        out["pe"] = -1.0
    return out


def load_manual(path=None) -> dict[str, dict]:
    p = path or ROOT / "data" / "fundamentals_manual.csv"   # versionado en el repo (no en la caché)
    try:
        df = pd.read_csv(p)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return {}
    out = {}
    for _, row in df.iterrows():
        out[str(row["ticker"]).upper()] = {k: _num(row.get(k)) for k in METRICAS}
    return out


def simbolo_fundamental(activo: dict) -> str | None:
    """Símbolo de yfinance del que sacar fundamentales: ticker BYMA para locales, subyacente para CEDEARs."""
    if activo.get("tipo") == "cedear":
        return activo.get("subyacente") or activo["ticker"]
    return f"{activo['ticker']}.BA"


def _leer_cache() -> dict:
    if CACHE.exists() and date.fromtimestamp(CACHE.stat().st_mtime) == date.today():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def _bajar_info(simbolo: str) -> tuple[str, dict | None]:
    try:
        import yfinance as yf
        return simbolo, from_yf_info(yf.Ticker(simbolo).info)
    except Exception as e:  # red caída, ticker deslistado, ETF sin datos, etc.
        print(f"  [aviso] fundamentales de {simbolo} no disponibles: {e}")
        return simbolo, None


def _bajar_yfinance(simbolos: list[str]) -> dict[str, dict]:
    cache = _leer_cache()
    faltan = [s for s in simbolos if s not in cache]
    if faltan:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for s, m in ex.map(_bajar_info, faltan):
                cache[s] = m or {}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {s: cache.get(s) or {} for s in simbolos}


def load_fundamentals(universe: list[dict], usar_yfinance: bool = True,
                      limites: dict | None = None) -> dict[str, dict]:
    """`limites`: {métrica: [min, max]} plausibles (settings fundamental.limites); default LIMITES."""
    lim = {k: tuple(v) for k, v in (limites or LIMITES).items()}
    manual = load_manual()
    simbolos = sorted({s for a in universe if (s := simbolo_fundamental(a))})
    yf_data = _bajar_yfinance(simbolos) if usar_yfinance else {}
    out: dict[str, dict] = {}
    for a in universe:
        t = a["ticker"]
        m: dict = {k: None for k in METRICAS}
        m.update({k: v for k, v in sanear(yf_data.get(simbolo_fundamental(a) or "", {}), lim).items() if v is not None})
        m.update({k: v for k, v in manual.get(t, {}).items() if v is not None})
        out[t] = m
    return out
