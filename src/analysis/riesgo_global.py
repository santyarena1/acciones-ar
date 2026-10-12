"""Régimen de riesgo GLOBAL (EE.UU. / mundo). Funciones puras, sin I/O.

Señales diarias, cada una 0..1 (1 = riesgo alto), calculadas solo con cierres ya cerrados:
- tendencia_sma200: el S&P 500 (SPY) debajo de su media de 200 ruedas.
- tendencia_10m:    SPY debajo de su media de 10 meses (cierres de fin de mes; regla clásica de Faber).
- vix:              nivel del VIX entre `vix_calmo` (0) y `vix_panico` (1).
- credito:          bonos de empresas riesgosas (HYG) contra Tesoro 7-10 años (IEF) debajo de su media de 200.
- curva:            tasa a 10 años menos tasa a 3 meses negativa (curva invertida).

Riesgo compuesto = promedio ponderado de las señales disponibles, suavizado con la media de las últimas
`persistencia_dias` ruedas (una señal tiene que sostenerse varios días para mover la cartera).
Fracción defensiva = 0 hasta `riesgo_desde`, sube lineal hasta `defensivo_max` en `riesgo_pleno`, en escalones de
`paso` y con histéresis: el nivel cambia solo si el valor nuevo se aleja más de medio escalón + `margen`.
Todo usa cierres diarios: dentro del día la respuesta no cambia (el operador corre cada 15 minutos).
"""
from __future__ import annotations

import math

import pandas as pd

SIMBOLOS = {"spy": "SPY", "vix": "^VIX", "hyg": "HYG", "ief": "IEF", "tnx": "^TNX", "irx": "^IRX"}
DEFAULTS = {
    "sma_dias": 200, "sma_meses": 10, "vix_calmo": 20.0, "vix_panico": 35.0, "credito_sma_dias": 200,
    "pesos": {"tendencia_sma200": 0.20, "tendencia_10m": 0.20, "vix": 0.25, "credito": 0.25, "curva": 0.10},
    "persistencia_dias": 5, "riesgo_desde": 0.25, "riesgo_pleno": 0.75, "defensivo_max": 0.8,
    "paso": 0.1, "margen": 0.05,
}


def cfg_riesgo(settings: dict) -> dict:
    t = (settings.get("tactico") or {}).get("riesgo_global") or {}
    return {**DEFAULTS, **t, "pesos": {**DEFAULTS["pesos"], **(t.get("pesos") or {})}}


def _limpia(s: pd.Series | None) -> pd.Series | None:
    if s is None:
        return None
    s = s.dropna()
    return s if not s.empty else None


def bajo_media(s: pd.Series, n: int) -> pd.Series:
    """1 si el cierre está debajo de su media de n ruedas, 0 si arriba, NaN sin historia suficiente."""
    m = s.rolling(n, min_periods=n).mean()
    return (s < m).astype(float).where(m.notna())


def bajo_media_mensual(s: pd.Series, meses: int) -> pd.Series:
    """Igual con cierres de fin de mes. Un día cualquiera usa el último mes TERMINADO (sin mirar el futuro)."""
    me = s.resample("ME").last()
    m = me.rolling(meses, min_periods=meses).mean()
    flag = (me < m).astype(float).where(m.notna())
    return flag.reindex(s.index.union(flag.index)).sort_index().ffill().reindex(s.index)


def escala_lineal(s: pd.Series, bajo: float, alto: float) -> pd.Series:
    return ((s - bajo) / (alto - bajo)).clip(0.0, 1.0)


def senales_riesgo(datos: dict[str, pd.Series], cfg: dict) -> pd.DataFrame:
    """datos: {'spy','vix','hyg','ief','tnx','irx'} -> cierres diarios. Columnas faltantes quedan NaN."""
    spy = _limpia(datos.get("spy"))
    if spy is None:
        return pd.DataFrame()
    idx = spy.index
    al = lambda s: s.reindex(idx.union(s.index)).sort_index().ffill(limit=5).reindex(idx)  # noqa: E731
    out = pd.DataFrame(index=idx)
    out["tendencia_sma200"] = bajo_media(spy, int(cfg["sma_dias"]))
    out["tendencia_10m"] = bajo_media_mensual(spy, int(cfg["sma_meses"]))
    if (vix := _limpia(datos.get("vix"))) is not None:
        out["vix"] = escala_lineal(al(vix), float(cfg["vix_calmo"]), float(cfg["vix_panico"]))
    hyg, ief = _limpia(datos.get("hyg")), _limpia(datos.get("ief"))
    if hyg is not None and ief is not None:
        out["credito"] = bajo_media(al(hyg) / al(ief), int(cfg["credito_sma_dias"]))
    tnx, irx = _limpia(datos.get("tnx")), _limpia(datos.get("irx"))
    if tnx is not None and irx is not None:
        dif = al(tnx) - al(irx)
        out["curva"] = (dif < 0).astype(float).where(dif.notna())
    return out


def riesgo_compuesto(senales: pd.DataFrame, pesos: dict[str, float], persistencia: int = 1) -> pd.Series:
    """Promedio ponderado de las señales disponibles cada día, suavizado con media de `persistencia` ruedas."""
    cols = [c for c in senales.columns if pesos.get(c, 0) > 0]
    if not cols:
        return pd.Series(dtype=float)
    w = pd.Series({c: float(pesos[c]) for c in cols})
    s = senales[cols]
    num = (s * w).sum(axis=1, min_count=1)
    den = s.notna().mul(w).sum(axis=1)
    r = (num / den.where(den > 0)).dropna()
    return r.rolling(max(1, int(persistencia)), min_periods=1).mean()


def defensivo_bruto(riesgo: float, cfg: dict) -> float:
    """Fracción del presupuesto de acciones que pasa a refugio (sin escalones)."""
    if riesgo is None or (isinstance(riesgo, float) and math.isnan(riesgo)):
        return 0.0
    desde, pleno = float(cfg["riesgo_desde"]), float(cfg["riesgo_pleno"])
    f = 1.0 if pleno <= desde else min(1.0, max(0.0, (riesgo - desde) / (pleno - desde)))
    return f * float(cfg["defensivo_max"])


def histeresis(valores: pd.Series, paso: float, margen: float, tope: float) -> pd.Series:
    """Recorre la serie y devuelve el nivel en escalones de `paso`: cambia solo si el valor se aleja del nivel
    vigente al menos medio escalón + margen. Determinístico y sin estado guardado (se recalcula con la historia)."""
    nivel, out = 0.0, []
    for v in valores:
        if v is not None and not math.isnan(v) and abs(v - nivel) >= paso / 2 + margen - 1e-9:
            nivel = min(tope, max(0.0, round(round(v / paso) * paso, 4)))
        out.append(nivel)
    return pd.Series(out, index=valores.index, dtype=float)


def serie_defensiva(datos: dict[str, pd.Series], cfg: dict) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """(señales diarias, riesgo suavizado, fracción defensiva con escalones e histéresis)."""
    sen = senales_riesgo(datos, cfg)
    if sen.empty:
        return sen, pd.Series(dtype=float), pd.Series(dtype=float)
    riesgo = riesgo_compuesto(sen, cfg["pesos"], int(cfg["persistencia_dias"]))
    bruto = riesgo.map(lambda r: defensivo_bruto(r, cfg))
    return sen, riesgo, histeresis(bruto, float(cfg["paso"]), float(cfg["margen"]), float(cfg["defensivo_max"]))


def _ultimo(s: pd.Series | None) -> float | None:
    s = _limpia(s)
    return None if s is None else float(s.iloc[-1])


def _motivos(sen: pd.Series, datos: dict[str, pd.Series], cfg: dict) -> list[str]:
    m = []
    if sen.get("tendencia_sma200") == 1:
        m.append("El S&P 500 está debajo de su tendencia de 200 ruedas")
    elif sen.get("tendencia_sma200") == 0:
        m.append("El S&P 500 está sobre su tendencia de 200 ruedas")
    if sen.get("tendencia_10m") == 1:
        m.append(f"y debajo de su promedio de {cfg['sma_meses']} meses")
    if (vix := _ultimo(datos.get("vix"))) is not None:
        nivel = "miedo alto" if vix >= cfg["vix_panico"] else "nervioso" if vix > cfg["vix_calmo"] else "tranquilo"
        m.append(f"el VIX (índice del miedo) está en {vix:.0f}: mercado {nivel}")
    if sen.get("credito") == 1:
        m.append("los bonos de empresas riesgosas pierden contra los del Tesoro (el crédito se está cerrando)")
    if sen.get("curva") == 1:
        m.append("la curva de tasas de EE.UU. está invertida (aviso de recesión, suele anticipar con mucho margen)")
    return m


def riesgo_global(datos: dict[str, pd.Series], settings: dict) -> dict:
    """Resumen para la corrida en vivo: riesgo 0..1, fracción defensiva, señales y motivos en castellano."""
    cfg = cfg_riesgo(settings)
    sen, riesgo, defensivo = serie_defensiva(datos, cfg)
    if riesgo.empty:
        return {"riesgo": None, "defensivo": 0.0, "senales": {}, "motivos": ["Sin datos del mercado global"],
                "fecha": None}
    ult = sen.loc[riesgo.index[-1]]
    return {"riesgo": round(float(riesgo.iloc[-1]), 3), "defensivo": round(float(defensivo.iloc[-1]), 2),
            "defensivo_sin_escalon": round(defensivo_bruto(float(riesgo.iloc[-1]), cfg), 3),
            "senales": {k: (None if pd.isna(v) else round(float(v), 2)) for k, v in ult.items()},
            "motivos": _motivos(ult, datos, cfg), "fecha": str(riesgo.index[-1].date())}
