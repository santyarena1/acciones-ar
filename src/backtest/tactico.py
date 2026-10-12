"""Backtest multi-activo de la asignación táctica, en USD. Funciones puras (los datos entran por parámetro).

Clases y sus aproximaciones (proxies) históricas:
- acciones_ar: canasta pareja de ADRs argentinos (GGAL, YPF, BMA, PAM, TEO, TGS, ...) disponibles en cada fecha.
- cedears:     ETFs de grupos (sector/región) en partes iguales; con rotación, inclinados por momentum relativo.
- bonos_usd:   bono sintético a partir del riesgo país + tasa a 10 años de EE.UU. (duration fija, cupón = TIR).
               Saltos de un día de más de `quiebre_pb` (canje 2020) se toman como cambio de índice, no de precio.
- pesos:       NO hay historia de Lecaps: se aproxima con letras del Tesoro de EE.UU. a 3 meses (^IRX). Esto
               es OPTIMISTA para los pesos en crisis argentinas (no captura devaluaciones).
- oro:         GLD.   caja: 0% en USD.
Las señales se calculan con datos hasta la fecha de decisión y se opera la rueda siguiente. Costo por lado sobre
lo operado. Las fechas de rebalanceo son fin de mes (o fin de semana con freq='W-FRI').
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..analysis.macro import asignacion_clases, regimen_macro
from ..analysis.riesgo_global import cfg_riesgo, serie_defensiva
from ..analysis.rotacion import cfg_rotacion, evaluar_grupos
from ..analysis.tactico import aplicar_tactico

ADRS_AR = ["GGAL", "YPF", "BMA", "PAM", "TEO", "TGS", "EDN", "IRS", "BBAR", "CRESY", "SUPV", "CEPU", "LOMA"]
SENALES = {"spy": "SPY", "vix": "^VIX", "hyg": "HYG", "ief": "IEF", "tnx": "^TNX", "irx": "^IRX"}
TRAMOS = {"2008 crisis global": ("2008-01-01", "2009-06-30"), "2011-2015": ("2011-01-01", "2015-12-31"),
          "2018-2019 crisis AR": ("2018-01-01", "2019-12-31"), "2020 covid": ("2020-01-01", "2020-12-31"),
          "2022 suba de tasas": ("2022-01-01", "2022-12-31"), "2023-2026": ("2023-01-01", "2026-12-31")}


def bono_sintetico(rp: pd.Series, tnx: pd.Series, duracion: float = 5.0, quiebre_pb: float = 800) -> pd.Series:
    """Índice de precio+cupón de un bono soberano en USD: P = (1+y)^-D con y = riesgo país + UST10."""
    idx = rp.index.union(tnx.index)
    y = (rp.reindex(idx).ffill() / 1e4 + tnx.reindex(idx).ffill() / 100).dropna()
    precio = (1 + y) ** (-duracion)
    r = precio.pct_change().fillna(0.0)
    salto = rp.reindex(y.index).ffill().diff().abs() > quiebre_pb
    r[salto] = 0.0
    dias = y.index.to_series().diff().dt.days.fillna(0)
    r = r + y.shift(1).fillna(y.iloc[0]) * dias / 365
    return (1 + r).cumprod()


def indice_tasa(irx: pd.Series) -> pd.Series:
    """Letra del Tesoro a 3 meses acumulada (^IRX en % anual)."""
    s = irx.dropna()
    dias = s.index.to_series().diff().dt.days.fillna(0)
    return (1 + s.shift(1).fillna(s.iloc[0]) / 100 * dias / 365).cumprod()


def indice_parejo(series: dict[str, pd.Series]) -> pd.Series:
    """Canasta pareja rebalanceada a diario de las series disponibles cada día."""
    panel = pd.DataFrame(series).sort_index().ffill(limit=5)
    r = panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    return (1 + r).cumprod()


def fechas_decision(idx: pd.DatetimeIndex, freq: str, desde: str) -> list[pd.Timestamp]:
    s = pd.Series(idx, index=idx)
    s = s[s.index >= pd.Timestamp(desde)]
    return list(s.groupby(s.index.to_period(freq[0] if freq != "W-FRI" else "W-FRI")).max())


def _ret(px: pd.Series, a: pd.Timestamp, b: pd.Timestamp) -> float | None:
    s = px.dropna()
    pa, pb = s.loc[:a], s.loc[:b]
    if pa.empty or pb.empty or pa.index[-1] < a - pd.Timedelta(days=7):
        return None
    return float(pb.iloc[-1] / pa.iloc[-1] - 1)


def preparar(px: dict[str, pd.Series], rp: pd.Series, ccl: pd.Series | None, oficial: pd.Series | None,
             grupos: dict[str, dict]) -> dict:
    """Arma los activos del backtest (series de precio en USD) y las series de señales."""
    activos = {f"AR:{t}": px[t] for t in ADRS_AR if t in px}
    activos.update({f"G:{g}": px[d["proxy"]] for g, d in grupos.items() if d.get("proxy") in px})
    activos["BONOS"] = bono_sintetico(rp, px["^TNX"])
    activos["TBILL"] = indice_tasa(px["^IRX"])
    activos["GLD"] = px["GLD"]
    return {"activos": activos, "senales": {k: px[s] for k, s in SENALES.items() if s in px},
            "merval_usd": indice_parejo({t: px[t] for t in ADRS_AR if t in px}), "rp": rp, "ccl": ccl,
            "oficial": oficial, "proxies": {d["proxy"]: px[d["proxy"]] for d in grupos.values() if d["proxy"] in px}}


def _corte(s: pd.Series | None, d) -> pd.Series | None:
    return None if s is None else s.loc[:d]


def _pesos_clase(datos: dict, d, var: dict, settings: dict, perfil: str, defensivo: pd.Series) -> tuple[dict, str]:
    regimen = "neutral"
    if var.get("ar_regimen"):
        regimen = regimen_macro(_corte(datos["rp"], d), _corte(datos["ccl"], d), _corte(datos["oficial"], d),
                                _corte(datos["merval_usd"], d), settings)["regimen"]
    base = asignacion_clases(perfil, regimen, settings)
    dfv = float(defensivo.loc[:d].iloc[-1]) if var.get("global") and not defensivo.loc[:d].empty else 0.0
    if "defensivo_fijo" in var:
        dfv = float(var["defensivo_fijo"])
    cfg = {**(settings.get("tactico") or {}), **(var.get("cfg_tactico") or {})}
    return aplicar_tactico(base, dfv, regimen, 0.0, cfg), regimen


def _pesos_grupos(datos: dict, d, var: dict, cfg_rot: dict, disponibles: list[str]) -> dict[str, float]:
    if not disponibles:
        return {}
    if not var.get("rotacion"):
        return {g: 1 / len(disponibles) for g in disponibles}
    ev = evaluar_grupos({p: s.loc[:d] for p, s in datos["proxies"].items()}, cfg_rot)
    m = {g: ev.get(g, {}).get("multiplicador", 1.0) for g in disponibles}
    tot = sum(m.values())
    return {g: v / tot for g, v in m.items()}


def _cartera(datos: dict, d, var: dict, settings: dict, perfil: str, defensivo: pd.Series,
             cfg_rot: dict) -> tuple[dict[str, float], dict]:
    """Pesos por activo en la fecha d (con datos hasta d)."""
    clases, regimen = _pesos_clase(datos, d, var, settings, perfil, defensivo)
    act = datos["activos"]
    vivo = lambda k: k in act and not act[k].loc[:d].dropna().empty and act[k].loc[:d].dropna().index[-1] >= d - pd.Timedelta(days=7)  # noqa: E731,E501
    ars = [k for k in act if k.startswith("AR:") and vivo(k)]
    grupos = [k[2:] for k in act if k.startswith("G:") and vivo(k)]
    w = {k: clases.get("acciones_ar", 0) / len(ars) for k in ars} if ars else {}
    w.update({f"G:{g}": clases.get("cedears", 0) * f for g, f in _pesos_grupos(datos, d, var, cfg_rot, grupos).items()})
    w.update({"BONOS": clases.get("bonos_usd", 0), "TBILL": clases.get("pesos", 0), "GLD": clases.get("oro", 0)})
    return {k: v for k, v in w.items() if v > 0}, {**clases, "regimen": regimen}


def simular(datos: dict, settings: dict, perfil: str, var: dict, freq: str = "ME", desde: str = "2008-01-01",
            costo_bps: float = 60) -> dict:
    """var: {'ar_regimen', 'global', 'rotacion'} (bool). Devuelve curva, pesos por clase y turnover."""
    cfg_g, cfg_rot = cfg_riesgo(settings), cfg_rotacion(settings)
    cfg_g = {**cfg_g, **(var.get("cfg_global") or {})}
    _, _, defensivo = serie_defensiva(datos["senales"], cfg_g)
    idx = datos["senales"]["spy"].dropna().index
    dec = fechas_decision(idx, freq, desde)
    ejec = [idx[min(idx.get_loc(d) + 1, len(idx) - 1)] for d in dec]
    valor, curva, hist, turnover, previos = 1.0, {}, {}, 0.0, {}
    for i in range(len(dec) - 1):
        w, info = _cartera(datos, dec[i], var, settings, perfil, defensivo, cfg_rot)
        t = sum(abs(w.get(k, 0) - previos.get(k, 0)) for k in set(w) | set(previos))
        turnover += t
        valor *= 1 - t * costo_bps / 1e4
        a, b = ejec[i], ejec[i + 1]
        rets = {k: (_ret(datos["activos"][k], a, b) or 0.0) for k in w}
        r = sum(w[k] * rets[k] for k in w)
        valor *= 1 + r
        previos = {k: w[k] * (1 + rets[k]) / (1 + r) for k in w}
        curva[b], hist[dec[i]] = valor, info
    curva = pd.Series(curva)
    anios = max((curva.index[-1] - curva.index[0]).days / 365.25, 1e-9)
    return {"curva": curva, "clases": pd.DataFrame(hist).T, "turnover_anual": turnover / anios}


def metricas(curva: pd.Series, por_anio: float) -> dict:
    if len(curva) < 3:
        return {}
    r = curva.pct_change().dropna()
    anios = len(r) / por_anio
    cagr = (curva.iloc[-1] / curva.iloc[0]) ** (1 / anios) - 1
    vol = float(r.std() * math.sqrt(por_anio))
    dd = float((curva / curva.cummax() - 1).min())
    return {"cagr": round(cagr, 4), "vol": round(vol, 4), "sharpe": round(cagr / vol, 2) if vol else np.nan,
            "max_dd": round(dd, 4), "calmar": round(cagr / abs(dd), 2) if dd < 0 else np.nan}


def por_tramos(curva: pd.Series, por_anio: float, tramos: dict = TRAMOS) -> dict[str, dict]:
    out = {}
    for nombre, (a, b) in tramos.items():
        sub = curva.loc[a:b]
        if len(sub) > 3:
            prev = curva.loc[:a].iloc[:-1] if len(curva.loc[:a]) > 1 else sub.iloc[:1]
            out[nombre] = metricas(pd.concat([prev.iloc[-1:], sub]) if not prev.empty else sub, por_anio)
    return out


def estudio_eventos(indice: pd.Series, fechas: list[str], dias_antes: int, dias_despues: int = 1) -> pd.DataFrame:
    """Retorno de la canasta argentina en la ventana previa (hasta el cierre anterior al evento) y en la reacción
    (del cierre anterior a `dias_despues` ruedas después). Sirve para ver si conviene cubrirse antes."""
    filas = []
    s = indice.dropna()
    for f in fechas:
        ts = pd.Timestamp(f)
        antes = s.loc[:ts - pd.Timedelta(days=1)]
        despues = s.loc[ts:]
        if len(antes) < dias_antes + 1 or len(despues) < dias_despues:
            continue
        ini = antes.loc[:ts - pd.Timedelta(days=dias_antes)]
        if ini.empty:
            continue
        filas.append({"evento": f, "ventana_previa": antes.iloc[-1] / ini.iloc[-1] - 1,
                      "reaccion": despues.iloc[dias_despues - 1] / antes.iloc[-1] - 1})
    return pd.DataFrame(filas)
