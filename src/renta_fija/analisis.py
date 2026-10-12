"""Análisis de renta fija sobre la tabla valuada (puro): curvas por familia, valor relativo, spread de legislación,
inflación breakeven (tasa fija vs. CER) y score 0-100 por instrumento."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from . import calidad

TAUS_NS = (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0)
MIN_PUNTOS_LOG = 3
PB = 10_000
PUNTOS_CURVA = 25
DEFAULTS = {"dias_min_curva": 20, "min_puntos_ns": 5, "rico_barato_pb": 50,
            "score": {"pesos": {"rendimiento": 0.40, "valor_relativo": 0.35, "liquidez": 0.25},
                      "spread_saturacion_pb": 150, "volumen_ref_ars": 5.0e9, "volumen_min_ars": 1.0e6}}


@dataclass(frozen=True)
class Curva:
    """Curva TIR(duration). tipo 'ns' = Nelson-Siegel con tau fijo; 'log' = a + b·ln(duration)."""
    tipo: str
    coef: tuple[float, ...]
    tau: float | None
    dur_min: float
    dur_max: float

    def tir(self, duration: float | np.ndarray) -> float | np.ndarray:
        escalar = np.ndim(duration) == 0
        x = np.maximum(np.atleast_1d(np.asarray(duration, dtype=float)), 1e-3)
        if self.tipo == "log":
            y = self.coef[0] + self.coef[1] * np.log(x)
        else:
            y = _base_ns(x, self.tau or 1.0) @ np.asarray(self.coef)
        return float(y[0]) if escalar else y


def _base_ns(x: np.ndarray, tau: float) -> np.ndarray:
    z = x / tau
    f1 = (1 - np.exp(-z)) / z
    return np.column_stack([np.ones_like(x), f1, f1 - np.exp(-z)])


def ajustar_curva(duration: np.ndarray, tir: np.ndarray, min_puntos_ns: int = 5) -> Curva | None:
    """Nelson-Siegel-lite (tau por grilla, betas por mínimos cuadrados) o logarítmica si hay pocos puntos."""
    x, y = np.asarray(duration, dtype=float), np.asarray(tir, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y) & (x > 0)
    x, y = x[ok], y[ok]
    if len(x) < MIN_PUNTOS_LOG:
        return None
    if len(x) < min_puntos_ns:
        b, a = np.polyfit(np.log(x), y, 1)
        return Curva("log", (float(a), float(b)), None, float(x.min()), float(x.max()))
    mejor: tuple[float, float, np.ndarray] | None = None
    for tau in TAUS_NS:
        base = _base_ns(x, tau)
        coef, *_ = np.linalg.lstsq(base, y, rcond=None)
        sse = float(np.sum((base @ coef - y) ** 2))
        if mejor is None or sse < mejor[0]:
            mejor = (sse, tau, coef)
    _, tau, coef = mejor
    return Curva("ns", tuple(float(v) for v in coef), tau, float(x.min()), float(x.max()))


def _params(params: dict[str, Any] | None) -> dict[str, Any]:
    p = {**DEFAULTS, **(params or {})}
    p["score"] = {**DEFAULTS["score"], **(params or {}).get("score", {})}
    p["score"]["pesos"] = {**DEFAULTS["score"]["pesos"], **p["score"].get("pesos", {})}
    return p


def _aptos_curva(df: pd.DataFrame, dias_min: int) -> pd.DataFrame:
    return df[df["tir"].notna() & df["duration"].notna() & (df["dias"] >= dias_min)]


def curvas_por_familia(df: pd.DataFrame, params: dict[str, Any] | None = None) -> dict[str, Curva]:
    """Una curva por familia, ajustada SOLO con datos válidos (sin precios viejos ni TIR absurdas)."""
    p = _params(params)
    aptos = _aptos_curva(df[calidad.datos_validos(df, params)], p["dias_min_curva"])
    out = {}
    for familia, g in aptos.groupby("familia"):
        curva = ajustar_curva(g["duration"].to_numpy(), g["tir"].to_numpy(), p["min_puntos_ns"])
        if curva is not None:
            out[str(familia)] = curva
    return out


def agregar_valor_relativo(df: pd.DataFrame, curvas: dict[str, Curva],
                           params: dict[str, Any] | None = None) -> pd.DataFrame:
    """tir_curva, spread_vs_curva_pb (+ = rinde más que la curva = barato) y senal_rv."""
    p = _params(params)

    def _tir_curva(fila: pd.Series) -> float | None:
        curva = curvas.get(fila["familia"])
        if curva is None or pd.isna(fila["duration"]) or fila["dias"] < p["dias_min_curva"]:
            return None
        return float(curva.tir(fila["duration"]))

    tir_curva = df.apply(_tir_curva, axis=1) if len(df) else pd.Series(dtype=float)
    spread = (df["tir"] - tir_curva.astype(float)) * PB
    umbral = p["rico_barato_pb"]
    senal = np.where(spread > umbral, "barato", np.where(spread < -umbral, "caro", "en_curva"))
    return df.assign(tir_curva=tir_curva.astype(float), spread_vs_curva_pb=spread.round(1),
                     senal_rv=np.where(spread.isna(), None, senal))


def agregar_spread_ley(df: pd.DataFrame) -> pd.DataFrame:
    """Spread de legislación (pb): TIR del Bonar (ley local) - TIR del Global par (ley NY). Va en ambas filas."""
    tir = df.set_index("ticker")["tir"]
    spreads = {}
    for _, f in df[df["par"].notna()].iterrows():
        par = f["par"]
        if par not in tir.index or pd.isna(f["tir"]) or pd.isna(tir[par]):
            continue
        local, ny = (f["tir"], tir[par]) if f["ley"] == "local" else (tir[par], f["tir"])
        spreads[f["ticker"]] = round((local - ny) * PB, 1)
    return df.assign(spread_ley_pb=df["ticker"].map(spreads))


def agregar_breakeven(df: pd.DataFrame, curva_cer: Curva | None) -> pd.DataFrame:
    """Inflación breakeven implícita: (1+TEA tasa fija)/(1+TIR real CER a igual duration) - 1 (anual y mensual)."""
    if curva_cer is None:
        return df.assign(breakeven_anual=np.nan, breakeven_mensual=np.nan)
    fija = (df["familia"] == "tasa_fija") & df["tir"].notna() & df["duration"].notna()
    real = pd.Series(np.nan, index=df.index)
    real[fija] = curva_cer.tir(df.loc[fija, "duration"].to_numpy())
    be = (1 + df["tir"]) / (1 + real) - 1
    be = be.where(fija)
    return df.assign(breakeven_anual=be, breakeven_mensual=(1 + be) ** (1 / 12) - 1)


def _percentil(serie: pd.Series) -> pd.Series:
    if serie.notna().sum() <= 1:
        return pd.Series(50.0, index=serie.index).where(serie.notna())
    return serie.rank(pct=True) * 100


def _score_liquidez(vol: pd.Series, vmin: float, vref: float) -> pd.Series:
    lo, hi = math.log10(float(vmin)), math.log10(float(vref))
    x = np.log10(vol.clip(lower=vmin).astype(float))
    return ((x - lo) / (hi - lo) * 100).clip(0, 100)


def agregar_score(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """score_rf 0-100 = rendimiento (percentil de carry en USD dentro de su clase) + valor relativo vs. curva
    + liquidez (log del volumen efectivo). Los pesos están en renta_fija.yaml.
    Lo que vence en menos de `dias_min_curva` días tiene TIR ruidosa: rendimiento 0 (sólo sirve como caja)."""
    p = _params(params)
    s = p["score"]
    comparables = df["carry_usd"].where((df["dias"] >= p["dias_min_curva"]) & calidad.datos_validos(df, params))
    rend = comparables.groupby(df["clase"]).transform(_percentil).fillna(0.0)
    sat = float(s["spread_saturacion_pb"])
    rv = (50 + 50 * (df["spread_vs_curva_pb"].astype(float) / sat).clip(-1, 1)).fillna(50.0)
    liq = _score_liquidez(df["volumen_ars"].fillna(0.0), s["volumen_min_ars"], s["volumen_ref_ars"])
    w = s["pesos"]
    total = (w["rendimiento"] * rend + w["valor_relativo"] * rv + w["liquidez"] * liq) / sum(w.values())
    total = total.where(df["tir"].notna())
    return df.assign(score_rendimiento=rend.round(1), score_valor_relativo=rv.round(1),
                     score_liquidez=liq.round(1), score_rf=total.round(1))


def aplicar_filtro_compra(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """`score_rf_bruto` conserva el score calculado; `score_rf` queda vacío si el instrumento no es apto para
    comprar (dato dudoso, precio viejo, iliquidez, vence ya). Así la asignación nunca elige un dato roto, y una
    tenencia que deja de ser apta no se vende por eso (queda fuera del ranking hasta que el dato vuelva)."""
    out = calidad.marcar_aptos(df, params)
    return out.assign(score_rf_bruto=out["score_rf"], score_rf=out["score_rf"].where(out["apto_compra"]))


def analizar(df: pd.DataFrame, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Tabla valuada -> tabla con valor relativo, spread de ley, breakeven, score y filtro de calidad."""
    if df.empty:
        return df
    curvas = curvas_por_familia(df, params)
    out = agregar_valor_relativo(df, curvas, params)
    out = agregar_spread_ley(out)
    out = agregar_breakeven(out, curvas.get("cer"))
    out = aplicar_filtro_compra(agregar_score(out, params), params)
    return out.sort_values(["clase", "score_rf"], ascending=[True, False], na_position="last").reset_index(drop=True)


def _puntos_curva(curva: Curva) -> list[dict[str, float]]:
    grilla = np.linspace(curva.dur_min, curva.dur_max, PUNTOS_CURVA)
    return [{"duration": round(float(d), 4), "tir": round(float(t), 6)} for d, t in zip(grilla, curva.tir(grilla))]


def resumen_curvas(df: pd.DataFrame, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Por clase: n, TIR media/mediana, duration media, puntos observados y curva ajustada por familia (para graficar)."""
    curvas = curvas_por_familia(df, params)
    out: dict[str, Any] = {}
    for clase, g in df[df["tir"].notna()].groupby("clase"):
        puntos = g.sort_values("duration")[["ticker", "familia", "duration", "tir"]]
        out[str(clase)] = {
            "n": int(len(g)),
            "tipo_tasa": str(g["tipo_tasa"].iloc[0]),
            "tir_media": float(g["tir"].mean()),
            "tir_mediana": float(g["tir"].median()),
            "duration_media": float(g["duration"].mean()),
            "puntos": puntos.to_dict("records"),
            "curvas": {f: _puntos_curva(curvas[f]) for f in g["familia"].unique() if f in curvas},
        }
        if "breakeven_mensual" in g and g["breakeven_mensual"].notna().any():
            out[str(clase)]["breakeven_mensual_medio"] = float(g["breakeven_mensual"].mean())
    return out
