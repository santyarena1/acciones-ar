"""Pesos objetivo para renta fija dentro del presupuesto de cada clase. Función pura.

- bonos_usd: soberanos en dólares y ONs en USD.
- pesos: LECAP / BONCAP / CER / duales.
Se eligen los N mejores por score_rf (con score mínimo), en partes iguales y con tope por instrumento.
Para no rotar de más, un instrumento que ya está en cartera se mantiene si sigue dentro de los mejores
`mantener_si_top` de su clase.
"""
from __future__ import annotations

import pandas as pd

CLASES_RF = {
    "bonos_usd": ("soberano_usd", "on_usd"),
    "pesos": ("lecap", "boncap", "cer", "dual"),
}
DEFAULTS = {"max_instrumentos": {"bonos_usd": 3, "pesos": 3}, "peso_max_instrumento": 0.12,
            "score_min": 50, "mantener_si_top": 6}


def _cfg(settings: dict) -> dict:
    return {**DEFAULTS, **(settings.get("renta_fija") or {})}


def _clases(cfg: dict) -> dict[str, tuple[str, ...]]:
    """`clases_pesos` (capa táctica en modo defensivo) restringe los pesos a letras/bonos cortos a tasa fija."""
    restr = cfg.get("clases_pesos")
    return {**CLASES_RF, "pesos": tuple(restr)} if restr else dict(CLASES_RF)


def _salir_de_excluidas(rf: pd.DataFrame, pesos_actuales: dict[str, float], cfg: dict) -> dict[str, float]:
    excluidas = set(CLASES_RF["pesos"]) - set(_clases(cfg)["pesos"])
    return {t: 0.0 for t in rf.index[rf["clase"].isin(excluidas)] if pesos_actuales.get(t, 0) > 0}


def objetivos_renta_fija(rf: pd.DataFrame | None, asignacion: dict[str, float],
                         pesos_actuales: dict[str, float], settings: dict) -> dict[str, float]:
    """rf: índice ticker, columnas 'clase' y 'score_rf'. Devuelve {ticker: peso objetivo}."""
    if rf is None or rf.empty or "score_rf" not in rf.columns:
        return {}
    cfg = _cfg(settings)
    out = _salir_de_excluidas(rf, pesos_actuales, cfg)
    for clase_cartera, clases in _clases(cfg).items():
        presupuesto = float(asignacion.get(clase_cartera, 0.0))
        sub = rf[rf["clase"].isin(clases) & rf["score_rf"].notna()].sort_values("score_rf", ascending=False)
        ranking = list(sub.index)
        en_cartera = [t for t in ranking if pesos_actuales.get(t, 0) > 0]
        for t in en_cartera:
            if ranking.index(t) >= cfg["mantener_si_top"]:
                out[t] = 0.0
        if presupuesto <= 0 or sub.empty:
            continue
        n_max = int(cfg["max_instrumentos"].get(clase_cartera, 3))
        aptos = [t for t in ranking if sub.at[t, "score_rf"] >= cfg["score_min"]]
        sostenidos = [t for t in en_cartera if ranking.index(t) < cfg["mantener_si_top"]]
        elegidos = (sostenidos + [t for t in aptos if t not in sostenidos])[:n_max]
        if not elegidos:
            continue
        w = min(presupuesto / len(elegidos), cfg["peso_max_instrumento"])
        out.update({t: round(w, 4) for t in elegidos})
    return out


def elegir_estacionamiento(rf: pd.DataFrame | None, dias_min: int = 20, dias_max: int = 120,
                           volumen_min: float = 1e9) -> str | None:
    """Lecap/Boncap corta para estacionar el efectivo: apta para compra, vence en [dias_min, dias_max] y con
    mucho volumen (se vende en el acto cuando hace falta la plata). Entre esas, la de mayor TEM."""
    if rf is None or rf.empty or not {"clase", "dias", "tem"} <= set(rf.columns):
        return None
    c = rf[rf["clase"].isin(["lecap", "boncap"]) & rf["dias"].between(dias_min, dias_max) & rf["tem"].notna()]
    if "apto_compra" in c.columns:
        c = c[c["apto_compra"].fillna(False).astype(bool)]
    if "volumen_ars" in c.columns:
        c = c[c["volumen_ars"].fillna(0) >= volumen_min]
    return str(c["tem"].idxmax()) if not c.empty else None


def objetivo_estacionamiento(targets: dict[str, float], rf: pd.DataFrame | None, valor_total: float,
                             settings: dict) -> dict[str, float]:
    """Lo que no tiene destino (más allá de la caja operativa) va a una Lecap corta en vez de quedar en pesos
    quietos. Devuelve {ticker: peso} a sumar a los objetivos (vacío si no corresponde)."""
    cfg = (settings.get("caja") or {})
    if not cfg.get("estacionar", True) or valor_total <= 0:
        return {}
    libre = 1.0 - sum(w for w in targets.values() if w > 0) - float(cfg.get("operativa", 0.02))
    minimo = float(settings["portfolio"].get("posicion_minima_ars") or 0) / valor_total
    t = elegir_estacionamiento(rf, cfg.get("dias_min", 20), cfg.get("dias_max", 120), cfg.get("volumen_min", 1e9))
    if t is None or libre < max(minimo, 0.0) or libre <= 0:
        return {}
    return {t: round(targets.get(t, 0.0) + libre, 4)}
