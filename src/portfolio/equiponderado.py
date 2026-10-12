"""Acciones argentinas equiponderadas (estrategia.acciones_ar = equiponderado). Función pura.

En el backtest 2018-2026 el score técnico NO le ganó al equiponderado en las locales (en ningún sub-período),
así que esta clase se arma como una cartera pareja de las N acciones más líquidas del panel líder.

- Elegibles: panel líder, líquidas y con datos sanos; se ordenan por monto operado promedio (20 ruedas).
- Se mantiene lo que está en cartera mientras siga dentro del puesto N + margen (evita rotar por ruido).
- Salidas: caer fuera de N + margen, no ser del panel líder, o alerta de STOP si `estrategia.salir_por_stop`
  (apagado por defecto: en el backtest el stop vendía en los pisos y recompraba después: -8,5% vs +9,0% anual).
- Con datos rotos (o sin fila en el ranking) no se toca: no se compra ni se vende, y ocupa presupuesto.
- Pesos iguales: presupuesto / cantidad elegida, con tope por acción. La banda de no operar la aplica el operador.
"""
from __future__ import annotations

import math

import pandas as pd

TEXTO_RAZON = "cartera pareja de las más líquidas del panel líder"


def _cfg(settings: dict) -> tuple[int, int]:
    e = settings.get("estrategia", {}) or {}
    return int(e.get("n_acciones_ar", 8)), int(e.get("margen_salida_liquidez", 3))


def _es_local(t: str, ranking: pd.DataFrame) -> bool:
    return t in ranking.index and str(ranking.at[t, "tipo"]) == "accion"


def _dato_roto(t: str, ranking: pd.DataFrame) -> bool:
    if t not in ranking.index:
        return True
    cal = ranking.at[t, "calidad_datos"] if "calidad_datos" in ranking.columns else ""
    return isinstance(cal, str) and cal.strip() != ""


def _ranking_liquidez(ranking: pd.DataFrame) -> list[str]:
    r = ranking[(ranking["tipo"] == "accion") & (ranking["panel"] == "lider")]
    r = r[r["liquido"].astype(bool) & r["vol_ars_20d"].notna()]
    r = r[[not _dato_roto(t, ranking) for t in r.index]]
    return list(r.sort_values("vol_ars_20d", ascending=False).index)


def _con_stop(t: str, ranking: pd.DataFrame, activo: bool = True) -> bool:
    if not activo:
        return False
    a = ranking.at[t, "alertas"] if "alertas" in ranking.columns and t in ranking.index else ""
    return isinstance(a, str) and "REVISAR STOP" in a


def objetivos_equiponderados(ranking: pd.DataFrame, pesos_actuales: dict[str, float], presupuesto: float,
                             settings: dict) -> dict[str, float]:
    """`pesos_actuales`: solo las acciones locales en cartera. Devuelve {ticker: peso objetivo}; las de datos
    rotos no aparecen (no se opera sobre ellas)."""
    n, margen = _cfg(settings)
    cap = settings["portfolio"]["peso_max_accion"]
    stop = bool((settings.get("estrategia") or {}).get("salir_por_stop", False))
    orden = _ranking_liquidez(ranking)
    puesto = {t: i + 1 for i, t in enumerate(orden)}
    tenidas = [t for t, w in pesos_actuales.items() if w > 0]
    intocables = [t for t in tenidas if _dato_roto(t, ranking)]
    quedan = [t for t in tenidas if t not in intocables and puesto.get(t, 10**9) <= n + margen
              and not _con_stop(t, ranking, stop)]
    nuevas = [t for t in orden if t not in quedan and not _con_stop(t, ranking, stop)][:max(0, n - len(quedan))]
    elegidas = quedan + nuevas
    libre = max(0.0, presupuesto - sum(pesos_actuales[t] for t in intocables))
    w = min(libre / len(elegidas), cap) if elegidas else 0.0
    out = {t: 0.0 for t in tenidas if t not in intocables}
    out.update({t: math.floor(w * 1e4 + 1e-6) / 1e4 for t in elegidas})  # hacia abajo
    return out
