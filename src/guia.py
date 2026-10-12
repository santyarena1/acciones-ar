"""Guía semanal en lenguaje llano. Determinística: arma texto a partir de los números, sin LLM.

Explica el contexto, cómo repartir la cartera, qué hacer esta semana y por qué.
"""
from __future__ import annotations

import math

import pandas as pd

from .portfolio.equiponderado import TEXTO_RAZON

NOMBRE_CLASE = {"acciones_ar": "Acciones argentinas", "cedears": "CEDEARs (empresas de afuera)",
                "bonos_usd": "Bonos en dólares", "pesos": "Pesos (Lecaps / CER)", "caja": "Caja",
                "oro": "Oro (refugio)"}
DESCARGO = "Herramienta de análisis personal: no es asesoramiento financiero. Las decisiones son tuyas."


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def razones(fila: pd.Series) -> list[str]:
    """Por qué el modelo ve bien (o mal) un activo, en frases cortas."""
    r = []
    if _ok(fila.get("tec_rel")) and fila["tec_rel"] >= 75:
        r.append(f"momentum mejor que el {fila['tec_rel']:.0f}% del universo")
    elif _ok(fila.get("tec_rel")) and fila["tec_rel"] <= 25:
        r.append("momentum entre los más flojos del universo")
    sobre = fila.get("sobre_sma200")
    sobre = None if not _ok(sobre) else bool(sobre)  # pandas puede traer numpy.bool_
    if sobre is True:
        r.append("en tendencia alcista (sobre su media de 200 ruedas, en USD)")
    elif sobre is False:
        r.append("en tendencia bajista (debajo de su media de 200 ruedas, en USD)")
    if _ok(fila.get("fund_rel")) and fila["fund_rel"] >= 70:
        r.append(f"fundamentales mejores que el {fila['fund_rel']:.0f}% de su grupo")
    elif _ok(fila.get("fund_rel")) and fila["fund_rel"] <= 30:
        r.append("fundamentales débiles frente a su grupo")
    if _ok(fila.get("upside_consenso")) and abs(fila["upside_consenso"]) >= 0.10:
        r.append(f"precio objetivo de analistas {fila['upside_consenso']:+.0%} vs. hoy")
    if _ok(fila.get("rsi14")) and fila["rsi14"] > 75:
        r.append(f"sobrecomprada en el corto plazo (RSI {fila['rsi14']:.0f})")
    return r


def _seccion_contexto(macro: dict, reporte: dict | None) -> list[str]:
    reg = macro.get("regimen", "sin datos")
    lineas = [f"## Contexto: régimen **{reg.upper()}** para Argentina"]
    if macro.get("motivos"):
        lineas.append("Por qué: " + "; ".join(macro["motivos"]) + ".")
    explic = {"favorable": "Se sube un poco el peso en activos argentinos.",
              "adverso": "Se baja el peso argentino y se cubre con CEDEARs y caja.",
              "neutral": "Se respeta el reparto de tu perfil sin ajustes."}
    lineas.append(explic.get(reg, "Faltan datos macro: se usa el reparto de tu perfil."))
    if reporte and reporte.get("resumen"):
        lineas.append(f"\n**Reporte semanal Gorostiaga n°{reporte.get('numero')}** ({reporte.get('fecha')}): "
                      f"{reporte['resumen'][:600]}")
    return lineas


def _seccion_tactica(tactico: dict | None) -> list[str]:
    """Capa táctica: riesgo global, sectores que lideran, eventos. Solo si se calculó."""
    if not tactico or not tactico.get("motivos"):
        return []
    r = tactico.get("riesgo")
    titulo = "## Mundo y sectores" + (f": riesgo global {r:.0%}" if r is not None else "")
    lineas = [titulo] + [f"- {m}" for m in tactico["motivos"]]
    base, final = tactico.get("asignacion_base") or {}, tactico.get("asignacion") or {}
    cambios = [f"{NOMBRE_CLASE.get(c, c)} {base.get(c, 0):.0%} → {w:.0%}" for c, w in final.items()
               if abs(w - base.get(c, 0)) >= 0.005]
    if cambios:
        lineas.append("Cambios sobre el reparto de tu perfil: " + "; ".join(cambios) + ".")
    return lineas


def _seccion_reparto(asignacion: dict, actual: dict, perfil: str) -> list[str]:
    lineas = [f"## Cómo repartir la cartera (perfil {perfil})", "| Clase | Hoy | Objetivo |", "|---|---|---|"]
    for c, w in asignacion.items():
        lineas.append(f"| {NOMBRE_CLASE.get(c, c)} | {actual.get(c, 0):.0%} | {w:.0%} |")
    return lineas


def _motivo_local_parejo(lado: str) -> str:
    if lado == "COMPRAR":
        return f" — {TEXTO_RAZON}"
    return f" — {TEXTO_RAZON}: salió del grupo de las más líquidas o tiene alerta de stop"


def _seccion_ordenes(ordenes: pd.DataFrame, ranking: pd.DataFrame, rf: pd.DataFrame | None,
                     estrategia_ar: str = "score") -> list[str]:
    if ordenes is None or ordenes.empty:
        return ["## Esta semana", "No hay movimientos sugeridos: la cartera está alineada con el objetivo."]
    lineas = ["## Esta semana"]
    for _, o in ordenes.iterrows():
        t = o["ticker"]
        verbo = "Comprar" if o["lado"] == "COMPRAR" else "Vender"
        detalle = f"**{verbo} {int(o['cantidad'])} {t}** (~${o['monto_ars']:,.0f})"
        if estrategia_ar == "equiponderado" and t in ranking.index and ranking.at[t, "tipo"] == "accion":
            detalle += _motivo_local_parejo(o["lado"])
        elif t in ranking.index:
            f = ranking.loc[t]
            motivos = razones(f) or ["score en zona de " + ("compra" if o["lado"] == "COMPRAR" else "salida")]
            detalle += f" — score {f['score']:.0f}: " + "; ".join(motivos)
        elif rf is not None and t in rf.index:
            f = rf.loc[t]
            tir = f.get("tir")
            detalle += f" — {f.get('clase', 'renta fija')}" + (f", TIR {tir:.1%}" if _ok(tir) else "")
        if o.get("nota"):
            detalle += f" ({o['nota']})"
        lineas.append(f"- {detalle}")
    return lineas


def _seccion_alertas(ranking: pd.DataFrame) -> list[str]:
    con = ranking[(ranking["en_cartera"]) & (ranking["alertas"].fillna("") != "")]
    if con.empty:
        return []
    return ["## Alertas de tu cartera"] + [f"- **{t}**: {a}" for t, a in con["alertas"].items()]


def _seccion_oportunidades(ranking: pd.DataFrame, n: int = 5, estrategia_ar: str = "score") -> list[str]:
    top = ranking[ranking["senal"] == "COMPRAR"]
    if estrategia_ar == "equiponderado":
        top = top[top["tipo"] != "accion"]   # las locales no se eligen por score
    top = top.head(n)
    if top.empty:
        return []
    lineas = ["## Mejores oportunidades del universo (fuera de tu cartera)"]
    for t, f in top.iterrows():
        lineas.append(f"- **{t}** ({f['tipo']}, {f['sector']}) score {f['score']:.0f}: " + "; ".join(razones(f)))
    return lineas


def generar_guia(macro: dict, asignacion: dict, actual_por_clase: dict, perfil: str, ranking: pd.DataFrame,
                 ordenes: pd.DataFrame, rf: pd.DataFrame | None = None, reporte: dict | None = None,
                 estrategia_ar: str = "score", tactico: dict | None = None) -> str:
    reparto = _seccion_reparto(asignacion, actual_por_clase, perfil)
    if estrategia_ar == "equiponderado":
        reparto.append(f"\nAcciones argentinas: {TEXTO_RAZON}, en partes iguales. En el backtest 2018-2026 "
                       "elegirlas por score no le ganó a tenerlas parejas; los CEDEARs sí se eligen por score.")
    tac = _seccion_tactica(tactico)
    partes = (_seccion_contexto(macro, reporte) + [""] + (tac + [""] if tac else []) + reparto
              + [""] + _seccion_ordenes(ordenes, ranking, rf, estrategia_ar) + [""] + _seccion_alertas(ranking)
              + [""] + _seccion_oportunidades(ranking, estrategia_ar=estrategia_ar) + ["", f"_{DESCARGO}_"])
    return "\n".join(partes)
