"""Pesos objetivo del portfolio de renta variable (acciones locales + CEDEARs).

La señal del análisis (`senal`) es la única fuente de verdad sobre qué hacer con cada activo:
- REDUCIR / VENDER                     -> peso objetivo 0 (salir)
- COMPRAR / AGREGAR y líquido          -> recibe asignación nueva
- cualquier otra (MANTENER, ESPERAR...) -> se mantiene el peso actual (con tope por activo)
Sin columna `senal` (tests / uso directo) se calcula con `scoring.signal`, con la misma histéresis.

Asignación nueva: proporcional a (score - comprar + 5), dividido por la volatilidad si sizing=score_vol.
Una posición en cartera con señal AGREGAR nunca queda por debajo de su peso actual (con tope): no se vende
lo mejor para hacer lugar. Con la columna opcional `mult_rotacion` (rotación por sector/región) el tamaño
nuevo y el orden para ocupar lugares se escalan por ese multiplicador. Cada clase (acciones_ar / cedears) reparte solo su presupuesto. Topes por
sector: se recorta primero lo nuevo y después lo que ya se tiene; lo liberado se redistribuye dentro de la
clase en sectores con lugar (no queda caja ociosa sin necesidad).
"""
from __future__ import annotations

import math

import pandas as pd

from ..analysis.scoring import SENALES_COMPRA, signal
from .orders import generate_orders  # noqa: F401  (se re-exporta: lo usan servicio y tests)

CLASE_DE_TIPO = {"accion": "acciones_ar", "cedear": "cedears"}
EPS = 1e-9
ITER_RELLENO = 6


def _cap_and_redistribute(raw: dict[str, float], budget: float, cap: float | dict[str, float],
                          max_iter: int = 50) -> dict[str, float]:
    """Reparte `budget` proporcional a `raw` sin que nadie supere su tope (`cap` común o por ticker)."""
    caps = cap if isinstance(cap, dict) else dict.fromkeys(raw, cap)
    alloc = dict.fromkeys(raw, 0.0)
    libres = {t: w for t, w in raw.items() if w > 0 and caps.get(t, 0.0) > EPS}
    restante = budget
    for _ in range(max_iter):
        if not libres or restante <= EPS:
            break
        tot = sum(libres.values())
        topados = [t for t, w in libres.items() if restante * w / tot >= caps[t]]
        if not topados:
            for t, w in libres.items():
                alloc[t] += restante * w / tot
            break
        for t in topados:
            alloc[t] = caps[t]
            restante -= caps[t]
            libres.pop(t)
    return alloc


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _senal(t: str, scores: pd.DataFrame, en_cartera: bool, liquido: bool, settings: dict) -> str:
    if "senal" in scores.columns:
        return str(scores.at[t, "senal"])
    return signal(float(scores.at[t, "score"]), en_cartera, None, settings, liquido, True)


def _crudo(t: str, s: float, scores: pd.DataFrame, settings: dict) -> float:
    crudo = s - settings["umbrales"]["comprar"] + 5
    vol = scores["vol_anual"].get(t) if "vol_anual" in scores.columns else None
    if settings["portfolio"].get("sizing") == "score_vol" and not _nan(vol) and vol and vol > 0:
        crudo /= max(vol, 0.10)
    return max(crudo, 0.1) * _mult_rotacion(t, scores)


def _mult_rotacion(t: str, scores: pd.DataFrame) -> float:
    """Inclinación por sector/región (capa táctica). Sin la columna, 1."""
    if "mult_rotacion" not in scores.columns:
        return 1.0
    m = scores["mult_rotacion"].get(t)
    return 1.0 if _nan(m) or m is None else float(m)


def _clasificar(scores: pd.DataFrame, pesos_actuales: dict[str, float], settings: dict) -> tuple[dict, ...]:
    """(fijos {t: peso a mantener}, candidatos {t: peso crudo}, pisos {t: peso actual de candidatos en cartera},
    intocables {t: peso actual}). Intocables: en cartera sin score (fuera del universo o sin datos): no se
    opera nada sin datos, ni siquiera el recorte por tope; solo ocupan presupuesto de su clase."""
    cap = settings["portfolio"]["peso_max_accion"]
    fijos, candidatos, pisos, intocables = {}, {}, {}, {}
    for t in sorted(set(scores.index) | set(pesos_actuales)):
        actual = pesos_actuales.get(t, 0.0)
        s = scores["score"].get(t, float("nan"))
        if t not in scores.index or _nan(s):
            if actual > 0:
                intocables[t] = actual
            continue
        liquido = bool(scores["liquido"].get(t, True)) if "liquido" in scores.columns else True
        senal = _senal(t, scores, actual > 0, liquido, settings)
        if senal.startswith("REDUCIR"):
            fijos[t] = 0.0
        elif senal in SENALES_COMPRA and liquido:
            candidatos[t] = _crudo(t, float(s), scores, settings)
            if actual > 0:
                pisos[t] = min(actual, cap)
        else:
            fijos[t] = min(actual, cap)
    return fijos, candidatos, pisos, intocables


def _limitar_posiciones(candidatos: dict, ocupadas: int, scores: pd.DataFrame, max_pos: int | None) -> dict:
    if max_pos is None:
        return candidatos
    libres = max(0, max_pos - ocupadas)
    orden = sorted(candidatos, key=lambda t: scores["score"].get(t, 0) * _mult_rotacion(t, scores), reverse=True)
    return {t: candidatos[t] for t in orden[:libres]}


def _achicar_base(fijos: dict, pisos: dict, presupuesto: float) -> tuple[dict, dict]:
    """Si lo que ya se tiene excede la clase, se recorta primero lo 'mantener' y después lo mejor."""
    exceso = sum(fijos.values()) + sum(pisos.values()) - presupuesto
    sf, sp = sum(fijos.values()), sum(pisos.values())
    f = max(0.0, sf - exceso) / sf if sf else 1.0
    resto = max(0.0, exceso - sf)
    g = max(0.0, sp - resto) / sp if sp else 1.0
    return {t: w * f for t, w in fijos.items()}, {t: w * g for t, w in pisos.items()}


def _repartir(fijos: dict, cand: dict, pisos: dict, presupuesto: float, cap: float, scores: pd.DataFrame,
              max_pos: int | None) -> tuple[dict, dict, dict]:
    """Una clase: devuelve (base, extra, elegibles). base = lo que se mantiene; extra = asignación nueva."""
    if sum(fijos.values()) + sum(pisos.values()) > presupuesto > 0:
        fijos, pisos = _achicar_base(fijos, pisos, presupuesto)
        return {**fijos, **pisos}, {}, {}
    base = {**fijos, **pisos}
    ocupadas = sum(1 for w in base.values() if w > 0)
    nuevos = _limitar_posiciones({t: w for t, w in cand.items() if t not in pisos}, ocupadas, scores, max_pos)
    elegibles = {**{t: cand[t] for t in pisos}, **nuevos}
    caps = {t: max(0.0, cap - pisos.get(t, 0.0)) for t in elegibles}
    extra = _cap_and_redistribute(elegibles, max(0.0, presupuesto - sum(base.values())), caps)
    return base, extra, elegibles


def _por_sector(base: dict, extra: dict, sectores: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for t in set(base) | set(extra):
        s = sectores.get(t, "otros")
        out[s] = out.get(s, 0.0) + base.get(t, 0.0) + extra.get(t, 0.0)
    return out


def _topes_sector(base: dict, extra: dict, sectores: dict[str, str], sec_cap: float) -> tuple[dict, dict]:
    base, extra = dict(base), dict(extra)
    for sec, total in _por_sector(base, extra, sectores).items():
        exceso = total - sec_cap
        if exceso <= EPS:
            continue
        ts = [t for t in set(base) | set(extra) if sectores.get(t, "otros") == sec]
        se = sum(extra.get(t, 0.0) for t in ts)
        f = max(0.0, se - exceso) / se if se else 1.0
        extra.update({t: extra[t] * f for t in ts if t in extra})
        resto = exceso - se * (1 - f)
        sb = sum(base.get(t, 0.0) for t in ts)
        if resto > EPS and sb:
            base.update({t: base[t] * max(0.0, sb - resto) / sb for t in ts if t in base})
    return base, extra


def _rellenar(base: dict, extra: dict, grupo: tuple, pisos: dict, cap: float, sectores: dict,
              sec_cap: float) -> tuple[dict, dict]:
    """Redistribuye dentro de la clase lo que liberaron los topes de sector, en sectores con lugar."""
    presupuesto, miembros, elegibles = grupo
    for _ in range(ITER_RELLENO):
        libre = presupuesto - sum(base.get(t, 0.0) + extra.get(t, 0.0) for t in miembros)
        if libre <= 1e-6 or not elegibles:
            break
        sec = _por_sector(base, extra, sectores)
        lugar = {t: min(cap - pisos.get(t, 0.0) - extra.get(t, 0.0), sec_cap - sec.get(sectores.get(t, "otros"), 0.0))
                 for t in elegibles}
        lugar = {t: r for t, r in lugar.items() if r > EPS}
        if not lugar:
            break
        add = _cap_and_redistribute({t: elegibles[t] for t in lugar}, libre, lugar)
        extra = {**extra, **{t: extra.get(t, 0.0) + a for t, a in add.items()}}
        base, extra = _topes_sector(base, extra, sectores, sec_cap)
    return base, extra


def _grupos(presupuestos: dict | None, tipos: dict, todos: set, p: dict) -> list[tuple[float, set, int | None]]:
    max_pos = p.get("max_posiciones_rv")
    if presupuestos is None:
        return [(max(0.0, 1.0 - p["caja_minima"]), set(todos), max_pos)]
    tot = sum(presupuestos.values())
    out = []
    for clase, total in presupuestos.items():
        miembros = {t for t in todos if CLASE_DE_TIPO.get(tipos.get(t, "accion")) == clase}
        tope = round(max_pos * total / tot) if max_pos and tot else None
        out.append((total, miembros, tope))
    return out


def build_targets(scores: pd.DataFrame, pesos_actuales: dict[str, float], sectores: dict[str, str],
                  settings: dict, presupuestos: dict[str, float] | None = None,
                  tipos: dict[str, str] | None = None) -> dict[str, float]:
    """scores: índice ticker, columna 'score' (y opcionales 'senal', 'liquido', 'vol_anual').
    presupuestos: {'acciones_ar': w, 'cedears': w}; si es None, todo es un solo bolsillo."""
    p = settings["portfolio"]
    cap, sec_cap = p["peso_max_accion"], p["peso_max_sector"]
    fijos, cand, pisos, intocables = _clasificar(scores, pesos_actuales, settings)
    base, extra, grupos = dict(fijos), {}, []
    for total, miembros, tope in _grupos(presupuestos, tipos or {}, set(fijos) | set(cand) | set(intocables), p):
        sub = lambda d: {t: w for t, w in d.items() if t in miembros}  # noqa: E731
        total = max(0.0, total - sum(sub(intocables).values()))
        tope = None if tope is None else max(0, tope - len(sub(intocables)))
        b, e, eleg = _repartir(sub(fijos), sub(cand), sub(pisos), total, cap, scores, tope)
        base.update(b)
        extra.update(e)
        grupos.append((total, miembros, eleg))
    base, extra = _topes_sector(base, extra, sectores, sec_cap)
    for g in grupos:
        base, extra = _rellenar(base, extra, g, pisos, cap, sectores, sec_cap)
    targets = {t: base.get(t, 0.0) + extra.get(t, 0.0) for t in set(base) | set(extra)}
    return {t: math.floor(w * 1e4 + 1e-6) / 1e4 for t, w in targets.items()}  # redondeo hacia abajo
