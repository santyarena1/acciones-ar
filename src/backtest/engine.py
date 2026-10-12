"""Backtest de rebalanceo mensual en USD.

Estrategia: a fin de cada mes se calcula el score TÉCNICO (absoluto + relativo al universo, igual que en vivo)
con datos hasta esa fecha (indicadores causales => sin lookahead). Lo que se tiene se mantiene mientras su score
no caiga debajo de `score_salida` (zona de mantener, como en vivo); los lugares libres hasta top_n se llenan con
lo mejor que pasa score_minimo y está sobre su SMA200, en partes iguales; el resto queda en caja (USD, 0%).
Se opera la rueda SIGUIENTE a la señal. Costos por lado sobre lo operado.

Benchmark: equiponderado de todo el universo disponible, rebalanceado mensualmente con los mismos costos.

Limitaciones (se muestran en el reporte):
- No usa fundamentales porque los actuales no son point-in-time.
- Sesgo de supervivencia: el universo es el de hoy.
"""
from __future__ import annotations

import math

import pandas as pd

from ..analysis.relative import mezclar, tecnico_relativo
from ..analysis.technical import compute_indicators, technical_score

WARMUP = 200
# Igual que en vivo con la config por defecto: se vende recién con score < vender (40) - histéresis (3), y no se
# abren posiciones bajo la SMA200. main.py debería pasarlos desde settings (umbrales).
SALIDA_VIVO = 37.0


def _panel(precios_usd: dict[str, pd.DataFrame]) -> pd.DataFrame:
    panel = pd.DataFrame({t: df["close"] for t, df in precios_usd.items()}).sort_index()
    return panel.ffill(limit=5)


def _fechas_rebalanceo(idx: pd.DatetimeIndex) -> set[pd.Timestamp]:
    s = pd.Series(idx, index=idx)
    return set(s.groupby([idx.year, idx.month]).max())


def _simular(panel: pd.DataFrame, elegir, costo: float, lag: int = 1) -> tuple[pd.Series, float, pd.Series]:
    """La cartera elegida con el cierre de d se opera `lag` ruedas después (en vivo se analiza con el cierre
    y se opera en la rueda siguiente): así el backtest no captura el movimiento que usó para decidir."""
    ret = panel.pct_change(fill_method=None).fillna(0.0)
    rebal = _fechas_rebalanceo(panel.index)
    valores, caja = pd.Series(0.0, index=panel.columns), 1.0
    curva, expo, turnover_total, pendientes = [], [], 0.0, {}
    for i, d in enumerate(panel.index):
        valores = valores * (1 + ret.loc[d])
        equity = float(valores.sum() + caja)
        if i >= WARMUP and d in rebal:
            pendientes[i + lag] = elegir(d, valores / equity).reindex(panel.columns).fillna(0.0)
        if i in pendientes:
            pesos_new = pendientes.pop(i)
            turnover = float((pesos_new - valores / equity).abs().sum())
            turnover_total += turnover
            equity -= turnover * costo * equity
            valores = pesos_new * equity
            caja = equity - float(valores.sum())
        curva.append(equity)
        expo.append(float(valores.sum()) / equity if equity else 0.0)
    idx = panel.index
    return pd.Series(curva, index=idx).iloc[WARMUP:], turnover_total, pd.Series(expo, index=idx).iloc[WARMUP:]


def metricas(curva: pd.Series) -> dict:
    if len(curva) < 2:
        return {}
    r = curva.pct_change().dropna()
    anios = (curva.index[-1] - curva.index[0]).days / 365.25
    total = curva.iloc[-1] / curva.iloc[0] - 1
    cagr = (1 + total) ** (1 / anios) - 1 if anios > 0 else float("nan")
    vol = r.std() * math.sqrt(252)
    dd = (curva / curva.cummax() - 1).min()
    neg = r[r < 0].std() * math.sqrt(252)
    return {
        "retorno_total": round(total, 4),
        "cagr": round(cagr, 4),
        "volatilidad": round(vol, 4),
        "sharpe_rf0": round(cagr / vol, 2) if vol > 0 else float("nan"),
        "sortino_rf0": round(cagr / neg, 2) if neg and neg > 0 else float("nan"),
        "max_drawdown": round(float(dd), 4),
        "calmar": round(cagr / abs(dd), 2) if dd < 0 else float("nan"),
    }


def rendimientos_anuales(curvas: pd.DataFrame) -> pd.DataFrame:
    fin = curvas.groupby(curvas.index.year).last()
    ini = curvas.groupby(curvas.index.year).first()
    prev = fin.shift(1).fillna(ini)
    return (fin / prev - 1).round(4)


def _scores_en_fecha(indicadores: dict[str, pd.DataFrame], d) -> tuple[pd.Series, pd.Series]:
    """(score técnico abs+rel como en vivo, ¿cierre sobre SMA200?) con datos hasta d."""
    filas = {t: ind.loc[d] for t, ind in indicadores.items() if d in ind.index and pd.notna(ind.at[d, "sma200"])}
    if not filas:
        return pd.Series(dtype=float), pd.Series(dtype=bool)
    ult = pd.DataFrame(filas).T
    abs_ = pd.Series({t: technical_score(ult.loc[t])["score"] for t in ult.index})
    return mezclar(abs_, tecnico_relativo(ult), 0.4), ult["close"] > ult["sma200"]


def _elegir_con_zona(scores: pd.Series, sobre: pd.Series, pesos: pd.Series, top_n: int, entrada: float,
                     salida: float | None, filtro_tendencia: bool) -> pd.Series:
    """Como en vivo: lo que se tiene se mantiene (con su peso) mientras score >= salida; los lugares libres se
    llenan con lo mejor que no se tiene y pasa la entrada (y la SMA200 si hay filtro). salida=None: se rearma
    el top-N desde cero cada mes (comportamiento viejo)."""
    tenidos = pesos[pesos > 1e-9]
    if salida is None:
        top = scores[scores >= entrada].sort_values(ascending=False).index[:top_n]
        return pd.Series({t: 1 / top_n for t in top}, dtype=float)
    quedan = scores.reindex(tenidos.index).dropna()
    quedan = quedan[quedan >= salida].sort_values(ascending=False).index[:top_n]
    out = {t: float(tenidos[t]) for t in quedan}
    nuevos = scores.drop(index=list(quedan), errors="ignore")
    nuevos = nuevos[nuevos >= entrada]
    if filtro_tendencia:
        nuevos = nuevos[sobre.reindex(nuevos.index).fillna(False).astype(bool)]
    libre = max(0.0, 1.0 - sum(out.values()))
    for t in nuevos.sort_values(ascending=False).index[:top_n - len(out)]:
        w = min(1 / top_n, libre)
        out[t], libre = w, libre - w
    return pd.Series(out, dtype=float)


def run_backtest(precios_usd: dict[str, pd.DataFrame], top_n: int = 6, score_minimo: float = 55,
                 costo_bps: float = 60, score_salida: float | None = SALIDA_VIVO, filtro_tendencia: bool = True) -> dict:
    """`score_salida`: zona de mantener como en vivo (None = rearmar el top-N todos los meses)."""
    panel = _panel(precios_usd)
    if len(panel) <= WARMUP + 21:
        raise ValueError(f"Historia insuficiente: {len(panel)} ruedas (mínimo {WARMUP + 21}).")
    costo = costo_bps / 1e4
    indicadores = {t: compute_indicators(panel[[t]].rename(columns={t: "close"}).dropna()) for t in panel.columns}

    def elegir_estrategia(d, pesos: pd.Series) -> pd.Series:
        s, sobre = _scores_en_fecha(indicadores, d)
        return _elegir_con_zona(s, sobre, pesos, top_n, score_minimo, score_salida, filtro_tendencia)

    def elegir_benchmark(d, _pesos=None) -> pd.Series:
        disp = [t for t in panel.columns if pd.notna(panel.at[d, t])]
        return pd.Series({t: 1 / len(disp) for t in disp}, dtype=float) if disp else pd.Series(dtype=float)

    return _resultado(panel, elegir_estrategia, elegir_benchmark, costo)


def _resultado(panel: pd.DataFrame, elegir, elegir_benchmark, costo: float) -> dict:
    curva_e, turn_e, expo = _simular(panel, elegir, costo)
    curva_b, _, _ = _simular(panel, elegir_benchmark, costo)
    meses = max(1, len(curva_e) / 21)
    me, mb = metricas(curva_e), metricas(curva_b)
    me["turnover_anual"] = round(turn_e / meses * 12, 2)
    me["exposicion_media"] = round(float(expo.mean()), 2)
    curvas = pd.DataFrame({"estrategia": curva_e, "benchmark": curva_b})
    mens = curvas.resample("ME").last().pct_change().dropna()
    me["meses_mejor_que_benchmark"] = round(float((mens["estrategia"] > mens["benchmark"]).mean()), 2) if len(mens) else None
    return {"estrategia": me, "benchmark": mb, "curvas": curvas, "anuales": rendimientos_anuales(curvas),
            "desde": str(curva_e.index[0].date()), "hasta": str(curva_e.index[-1].date())}


# --- acciones AR equiponderadas por liquidez (estrategia.acciones_ar = equiponderado) -------------------------

def _liquidas_en_fecha(montos: dict[str, pd.Series], d, tenidas: set[str], n: int, margen: int,
                       excluir: set[str] | None = None) -> list[str]:
    """Las N más líquidas con el monto operado promedio de las 20 ruedas HASTA d (sin lookahead). Las tenidas
    se quedan mientras estén dentro del puesto N + margen."""
    excluir = excluir or set()
    prom = {t: float(s.loc[:d].tail(20).mean()) for t, s in montos.items() if len(s.loc[:d]) >= 10}
    orden = [t for t in sorted(prom, key=prom.get, reverse=True) if pd.notna(prom[t]) and t not in excluir]
    puesto = {t: i + 1 for i, t in enumerate(orden)}
    quedan = [t for t in orden if t in tenidas and puesto[t] <= n + margen]
    return quedan + [t for t in orden if t not in quedan][:max(0, n - len(quedan))]


def _con_stop(indicadores: dict[str, pd.DataFrame], d, stop: float) -> set[str]:
    out = set()
    for t, ind in indicadores.items():
        if d in ind.index:
            f = ind.loc[d]
            if pd.notna(f["dist_max_52s"]) and f["dist_max_52s"] <= stop and pd.notna(f["sma200"])                     and f["close"] < f["sma200"]:
                out.add(t)
    return out


def run_backtest_equiponderado(precios_usd: dict[str, pd.DataFrame], montos_ars: dict[str, pd.Series],
                               candidatos: set[str], n: int = 8, margen: int = 3, costo_bps: float = 60,
                               banda: float = 0.02, stop: float = -9.0) -> dict:
    """Pareja de las N más líquidas de `candidatos` (panel líder), mensual, con banda de no operar.
    Benchmark: equiponderado de TODO el universo con los mismos costos (igual que run_backtest).
    `stop`: caída desde el máximo de 52 semanas (bajo SMA200) que saca la acción; -9 = sin stop (default)."""
    panel = _panel(precios_usd)
    if len(panel) <= WARMUP + 21:
        raise ValueError(f"Historia insuficiente: {len(panel)} ruedas (mínimo {WARMUP + 21}).")
    ind = {t: compute_indicators(panel[[t]].rename(columns={t: "close"}).dropna()) for t in panel.columns}
    montos = {t: s for t, s in montos_ars.items() if t in candidatos and t in panel.columns}

    def elegir(d, pesos: pd.Series) -> pd.Series:
        disp = {t for t in montos if pd.notna(panel.at[d, t])}
        tenidas = set(pesos[pesos > 1e-9].index)
        sel = _liquidas_en_fecha({t: montos[t] for t in disp}, d, tenidas, n, margen, _con_stop(ind, d, stop))
        w = 1 / n
        return pd.Series({t: (float(pesos[t]) if t in tenidas and abs(pesos[t] - w) <= banda else w) for t in sel},
                         dtype=float)

    def elegir_benchmark(d, _pesos=None) -> pd.Series:
        disp = [t for t in panel.columns if pd.notna(panel.at[d, t])]
        return pd.Series({t: 1 / len(disp) for t in disp}, dtype=float) if disp else pd.Series(dtype=float)

    return _resultado(panel, elegir, elegir_benchmark, costo_bps / 1e4)
