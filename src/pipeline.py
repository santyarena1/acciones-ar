"""Orquestación: datos -> indicadores -> scores (absolutos + relativos) -> señales -> alertas."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .analysis.fundamental import fundamental_score
from .analysis.relative import fundamental_relativo, mezclar, tecnico_relativo
from .analysis.scoring import alertas, combined_score, signal
from .analysis.technical import compute_indicators, technical_score
from .data.prices import (desvio_ratio_cedear, diagnostico_calidad, limpiar_picos, load_ccl, load_many,
                          ruedas_cerradas, to_usd, volumen_ars_promedio)

MIN_RUEDAS = 30
SECTORES_SIN_BALANCE = {"etf_indices", "etf_sector", "metales"}
TZ_AR = ZoneInfo("America/Argentina/Buenos_Aires")
# Ventas de las locales: nominales en pesos (inflación) -> no se puntúan en absoluto, solo relativo entre locales
EXCLUIR_ABS_LOCALES = {"revenue_growth"}


@dataclass
class Precios:
    usd: dict[str, pd.DataFrame] = field(default_factory=dict)      # serie en USD para analizar
    ultimo_ars: dict[str, float] = field(default_factory=dict)      # último precio en BYMA (para órdenes)
    vol_ars: dict[str, float] = field(default_factory=dict)         # monto operado diario promedio en ARS
    ccl: pd.Series | None = None
    merval_usd: pd.Series | None = None
    calidad: dict[str, str] = field(default_factory=dict)          # ticker -> motivo por el que no se opera
    monto_ars: dict[str, pd.Series] = field(default_factory=dict)  # monto operado diario en ARS (backtest)


def _cfg_datos(settings: dict) -> dict:
    return settings.get("datos", {}) or {}


def _ahora_ar() -> datetime:
    return datetime.now(TZ_AR).replace(tzinfo=None)


def _hora(texto: str) -> dtime:
    h, m = str(texto).split(":")
    return dtime(int(h), int(m))


def _calidad_cedear(ars: pd.DataFrame | None, sub: pd.DataFrame | None, ccl: pd.Series, cfg: dict) -> str:
    if ars is None or sub is None or ars.empty or sub.empty or ccl is None or ccl.empty:
        return ""
    dev = desvio_ratio_cedear(ars["close"], sub["close"], ccl)
    if dev is not None and abs(dev) > cfg.get("desvio_ccl_cedear_max", 0.05):
        return f"CCL implícito del CEDEAR desfasado {dev:+.1%} (precio viejo o cambio de ratio)"
    return ""


def _desde(settings: dict) -> date:
    return date.today() - timedelta(days=int(365 * settings["datos"]["historia_anios"]) + 30)


def _serie_usd(a: dict, ars: pd.DataFrame | None, hist: dict, ccl: pd.Series, cfg: dict) -> pd.DataFrame | None:
    """Serie en USD para analizar: sin prints aislados y solo con ruedas cerradas."""
    if a["tipo"] == "cedear":
        usd = hist.get(a["subyacente"])
    else:
        usd = to_usd(limpiar_picos(ars, cfg.get("umbral_pico", 0.30)), ccl) if ars is not None else None
    if usd is None or usd.empty:
        return None
    return ruedas_cerradas(usd, _ahora_ar(), _hora(cfg.get("hora_ruedas_cerradas", "18:00")))


def load_prices(universe: list[dict], settings: dict, iol_client=None) -> Precios:
    """Baja todo en lote. Locales: ARS/CCL. CEDEARs: subyacente en USD (y el CEDEAR en ARS para órdenes).
    Marca en `calidad` los activos con precio viejo, salto implausible, sin operaciones o CEDEAR desfasado."""
    desde, cfg = _desde(settings), _cfg_datos(settings)
    ttl = cfg.get("ttl_precios_min")
    ccl = load_ccl(desde, ttl_min=ttl)
    simbolos = [f"{a['ticker']}.BA" for a in universe] + [a["subyacente"] for a in universe if a["tipo"] == "cedear"]
    hist = load_many(simbolos + ["^MERV"], desde, ttl_min=ttl)
    p, hoy = Precios(ccl=ccl), _ahora_ar().date()
    for a in universe:
        t = a["ticker"]
        ars = hist.get(f"{t}.BA")
        if ars is not None and not ars.empty:
            p.ultimo_ars[t] = float(ars["close"].iloc[-1])
            if (v := volumen_ars_promedio(ars)) is not None:
                p.vol_ars[t] = v
            if "volume" in ars.columns:
                p.monto_ars[t] = (ars["close"] * ars["volume"]).dropna()
        motivo = diagnostico_calidad(ars, hoy, cfg)
        if not motivo and a["tipo"] == "cedear":
            motivo = _calidad_cedear(ars, hist.get(a["subyacente"]), ccl, cfg)
        if motivo:
            p.calidad[t] = motivo
        usd = _serie_usd(a, ars, hist, ccl, cfg)
        if usd is None or usd.empty:
            print(f"  [aviso] sin precios para {t}")
            continue
        p.usd[t] = usd
    if (m := hist.get("^MERV")) is not None:
        p.merval_usd = to_usd(m, ccl)["close"]
    return p


def _indicadores(precios_usd: dict[str, pd.DataFrame], tickers: list[str]) -> pd.DataFrame:
    filas = {}
    for t in tickers:
        df = precios_usd.get(t)
        if df is not None and len(df) >= MIN_RUEDAS:
            filas[t] = compute_indicators(df).iloc[-1]
    return pd.DataFrame(filas).T if filas else pd.DataFrame()


def _scores_tecnicos(ult: pd.DataFrame, tickers: list[str], settings: dict) -> pd.DataFrame:
    abs_ = pd.Series({t: technical_score(ult.loc[t])["score"] if t in ult.index else np.nan for t in tickers})
    cfg = settings.get("tecnico", {})
    rel = tecnico_relativo(ult, cfg.get("min_activos_relativo", 8)) if not ult.empty else pd.Series(dtype=float)
    return pd.DataFrame({"tec_abs": abs_, "tec_rel": rel.reindex(abs_.index),
                         "score_tecnico": mezclar(abs_, rel.reindex(abs_.index), cfg.get("peso_relativo", 0.4))})


def _scores_fundamentales(fund: dict[str, dict], universe: list[dict], settings: dict) -> pd.DataFrame:
    tickers = [a["ticker"] for a in universe]
    sect = pd.Series({a["ticker"]: a["sector"] for a in universe})
    grupos = pd.Series({a["ticker"]: a["tipo"] for a in universe})
    abs_r = {t: fundamental_score(fund.get(t, {}), sect.get(t), EXCLUIR_ABS_LOCALES if grupos.get(t) == "accion" else None)
             for t in tickers}
    abs_ = pd.Series({t: r["score"] for t, r in abs_r.items()})
    cfg = settings.get("fundamental", {})
    metricas = pd.DataFrame({t: fund.get(t, {}) for t in tickers}).T.apply(pd.to_numeric, errors="coerce")
    rel = fundamental_relativo(metricas, grupos, sect, cfg.get("min_activos_relativo", 6))
    return pd.DataFrame({"fund_abs": abs_, "fund_rel": rel,
                         "score_fundamental": mezclar(abs_, rel, cfg.get("peso_relativo", 0.5)),
                         "cobertura_fund": pd.Series({t: r["cobertura"] for t, r in abs_r.items()})})


def _num(x, nd: int = 3):
    return round(float(x), nd) if x is not None and pd.notna(x) else None


def _senal_final(senal: str, motivo: str, en_cartera: bool) -> str:
    """Con datos dudosos no se opera: lo que está en cartera se mantiene y lo que no, no se compra."""
    if not motivo:
        return senal
    return "MANTENER (datos dudosos)" if en_cartera else "DATOS DUDOSOS (no comprar)"


def analyze(precios_usd: dict[str, pd.DataFrame], fundamentales: dict[str, dict], universe: list[dict],
            settings: dict, horizonte: str, en_cartera: set[str] | None = None,
            vol_ars: dict[str, float] | None = None, contexto: dict[str, dict] | None = None,
            ultimo_ars: dict[str, float] | None = None, calidad: dict[str, str] | None = None) -> pd.DataFrame:
    en_cartera, vol_ars, contexto, ultimo_ars = en_cartera or set(), vol_ars or {}, contexto or {}, ultimo_ars or {}
    calidad = calidad or {}
    tickers = [a["ticker"] for a in universe]
    ult = _indicadores(precios_usd, tickers)
    tec = _scores_tecnicos(ult, tickers, settings)
    fun = _scores_fundamentales(fundamentales, universe, settings)
    vmin = settings.get("liquidez", {}).get("volumen_min_ars_dia", 0)
    filas = []
    for a in universe:
        t = a["ticker"]
        ind = ult.loc[t].to_dict() if t in ult.index else {}
        comb = combined_score(tec.at[t, "score_tecnico"], fun.at[t, "score_fundamental"],
                              fun.at[t, "cobertura_fund"], horizonte, settings,
                              aplica_fundamental=a["sector"] not in SECTORES_SIN_BALANCE)
        rsi_v = _num(ind.get("rsi14"), 1)
        sobre = bool(ind["close"] > ind["sma200"]) if pd.notna(ind.get("sma200", np.nan)) else None
        con_balance = a["sector"] not in SECTORES_SIN_BALANCE
        vol = vol_ars.get(t)
        liquido = vol is None and not vol_ars or (vol is not None and vol >= vmin)
        ctx = contexto.get(t, {})
        motivo = calidad.get(t) or ("" if pd.notna(tec.at[t, "score_tecnico"]) else "sin historia de precios")
        senal = signal(comb["score"], t in en_cartera, rsi_v, settings, liquido, sobre)
        filas.append({
            "ticker": t, "tipo": a["tipo"], "panel": a["panel"], "sector": a["sector"],
            "score": comb["score"],
            "senal": _senal_final(senal, motivo, t in en_cartera), "calidad_datos": motivo,
            "score_tecnico": tec.at[t, "score_tecnico"], "tec_abs": tec.at[t, "tec_abs"], "tec_rel": tec.at[t, "tec_rel"],
            "score_fundamental": fun.at[t, "score_fundamental"] if con_balance else np.nan,
            "fund_abs": fun.at[t, "fund_abs"] if con_balance else np.nan,
            "fund_rel": fun.at[t, "fund_rel"] if con_balance else np.nan,
            "cobertura_fund": fun.at[t, "cobertura_fund"] if con_balance else 0.0,
            "precio_usd": _num(ind.get("close")), "precio_ars": _num(ultimo_ars.get(t), 2),
            "rsi14": rsi_v, "mom_3m": _num(ind.get("mom_3m")), "mom_6m": _num(ind.get("mom_6m")),
            "mom_12m_1m": _num(ind.get("mom_12m_1m")), "vol_anual": _num(ind.get("vol_anual")),
            "dist_max_52s": _num(ind.get("dist_max_52s")),
            "sobre_sma200": sobre,
            "vol_ars_20d": _num(vol, 0), "liquido": bool(liquido),
            "upside_consenso": _num(ctx.get("upside_consenso")),
            "eventos": ", ".join(ctx.get("eventos", [])),
            "alertas": " | ".join(alertas(ind, t in en_cartera, ctx.get("eventos"), settings)),
            "en_cartera": t in en_cartera, "nota": comb["nota"],
        })
    return pd.DataFrame(filas).set_index("ticker").sort_values("score", ascending=False)
