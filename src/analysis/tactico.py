"""Asignación TÁCTICA por clase: arriba del perfil + régimen argentino. Funciones puras, sin I/O.

1. Eventos (elecciones, etc.): durante la ventana previa se baja la exposición argentina (acciones y bonos en
   dólares) en `reduccion_ar` y se pasa a CEDEARs / caja (`eventos.destino`).
2. Riesgo global: la fracción `defensivo` del presupuesto de acciones (argentinas + CEDEARs) pasa a refugio.
   Los bonos argentinos en dólares NO son refugio en una crisis global (caen con el riesgo país): se recortan con
   `bonos_usd_factor` (más si el régimen argentino es adverso). El refugio se reparte entre pesos cortos
   (Lecaps/Boncaps), oro (CEDEAR de GLD) y caja; con régimen argentino adverso pesa más el oro (los pesos también
   sufren si hay devaluación).
"""
from __future__ import annotations

from datetime import date

from .eventos import eventos_activos, proximos, reduccion_ar, texto_evento
from .riesgo_global import SIMBOLOS, riesgo_global
from .rotacion import cfg_rotacion, rotacion

CLASES_ACCIONES = ("acciones_ar", "cedears")
CLASES_AR = ("acciones_ar", "bonos_usd")
DEFAULT_REFUGIO = {"normal": {"pesos": 0.5, "oro": 0.3, "caja": 0.2},
                   "ar_adverso": {"oro": 0.6, "pesos": 0.2, "caja": 0.2}}
DEFAULT_BONOS = {"normal": 0.5, "ar_adverso": 1.0}
DEFAULT_DESTINO_EVENTO = {"cedears": 0.7, "caja": 0.3}
NOMBRE_REFUGIO = {"pesos": "Lecaps/Boncaps", "oro": "oro", "caja": "caja"}


def _mover(asig: dict, quitar: dict[str, float], destino: dict[str, float]) -> dict[str, float]:
    """Saca `quitar[c]` de cada clase y lo reparte según `destino` (fracciones que suman 1). No modifica `asig`."""
    out = dict(asig)
    total = sum(quitar.values())
    for c, m in quitar.items():
        out[c] = out.get(c, 0.0) - m
    tot_dest = sum(destino.values()) or 1.0
    for c, f in destino.items():
        out[c] = out.get(c, 0.0) + total * f / tot_dest
    return out


def aplicar_tactico(base: dict[str, float], defensivo: float, regimen_ar: str, reduccion_eventos: float,
                    cfg: dict) -> dict[str, float]:
    """Pesos por clase después de eventos y riesgo global. Siempre incluye la clase 'oro'. Suma lo mismo que base."""
    clave = "ar_adverso" if regimen_ar == "adverso" else "normal"
    out = {**base, "oro": base.get("oro", 0.0)}
    ev = min(1.0, max(0.0, float(reduccion_eventos or 0.0)))
    if ev > 0:
        destino = (cfg.get("eventos") or {}).get("destino") or DEFAULT_DESTINO_EVENTO
        out = _mover(out, {c: out.get(c, 0.0) * ev for c in CLASES_AR}, destino)
    d = min(1.0, max(0.0, float(defensivo or 0.0)))
    if d > 0:
        f_bonos = float({**DEFAULT_BONOS, **(cfg.get("bonos_usd_factor") or {})}[clave])
        quitar = {c: out.get(c, 0.0) * d for c in (cfg.get("clases_defensivas") or CLASES_ACCIONES)}
        quitar["bonos_usd"] = out.get("bonos_usd", 0.0) * min(1.0, d * f_bonos)
        refugio = {**DEFAULT_REFUGIO, **(cfg.get("refugio") or {})}[clave]
        out = _mover(out, quitar, refugio)
    return {c: round(max(0.0, v), 4) for c, v in out.items()}


def consolidar_minimos(asig: dict[str, float], valor_total: float, posicion_minima: float,
                       clases: tuple[str, ...] = ("oro",), destino: str = "pesos") -> dict[str, float]:
    """Una clase de una sola posición (oro) que no llega a la posición mínima se suma a `destino`."""
    out = dict(asig)
    if valor_total <= 0 or posicion_minima <= 0:
        return out
    for c in clases:
        if 0 < out.get(c, 0.0) and out[c] * valor_total < posicion_minima:
            out[destino] = round(out.get(destino, 0.0) + out[c], 4)
            out[c] = 0.0
    return out


def _motivo_riesgo(riesgo: dict | None, aplicado: float, calculado: float, regla_on: bool, regimen_ar: str,
                   cfg: dict) -> list[str]:
    if not riesgo or riesgo.get("riesgo") is None:
        return ["Sin datos del mercado global: no se aplica la regla de refugio."] if regla_on else []
    base = "; ".join(riesgo.get("motivos") or [])
    if aplicado > 0:
        clave = "ar_adverso" if regimen_ar == "adverso" else "normal"
        ref = {**DEFAULT_REFUGIO, **(cfg.get("refugio") or {})}[clave]
        destinos = ", ".join(NOMBRE_REFUGIO.get(c, c) for c, f in ref.items() if f > 0)
        return [f"{base}: paso {aplicado:.0%} de las acciones a refugio ({destinos})."]
    if calculado > 0 and not regla_on:
        return [f"{base}: la regla de refugio sugeriría pasar {calculado:.0%} de las acciones a refugio, pero está "
                "apagada (en la prueba histórica no mejoró lo suficiente)."]
    return [f"{base}: riesgo global bajo, no se mueve nada a refugio."]


def _motivo_eventos(eventos: list[dict], reduccion: float) -> list[str]:
    if not eventos:
        return []
    nombres = "; ".join(texto_evento(e) for e in eventos)
    extra = f" Bajo {reduccion:.0%} lo argentino hasta que pase." if reduccion else " Solo aviso: no cambia la cartera."
    return [f"Se viene: {nombres}.{extra}"]


def _motivo_rotacion(rot: dict | None, regla_on: bool) -> list[str]:
    if not rot or not rot.get("motivos"):
        return []
    return list(rot["motivos"]) if regla_on else [f"(Solo informativo, la regla está apagada) {m}"
                                                   for m in rot["motivos"]]


def resolver_tactico(base: dict[str, float], regimen_ar: str, series: dict, sectores_cedears: dict[str, str],
                     eventos: list[dict], hoy: date, settings: dict) -> dict:
    """Todo lo táctico de una corrida: asignación final por clase + lo que hay que mostrar (meta['tactico'])."""
    cfg = settings.get("tactico") or {}
    on_rg = bool((cfg.get("riesgo_global") or {}).get("aplicar"))
    cfg_rot, cfg_ev = cfg_rotacion(settings), cfg.get("eventos") or {}
    on_rot, on_ev = bool(cfg_rot.get("aplicar")), bool(cfg_ev.get("aplicar"))
    rg = riesgo_global({k: series.get(s) for k, s in SIMBOLOS.items()}, settings)
    defensivo = float(rg["defensivo"]) if on_rg and rg["riesgo"] is not None else 0.0
    rot = rotacion(series, sectores_cedears, cfg_rot) if cfg_rot.get("grupos") else None
    activos, prox = eventos_activos(eventos, hoy), proximos(eventos, hoy, int(cfg_ev.get("mostrar_dias", 60)))
    red = reduccion_ar(activos) if on_ev else 0.0
    asig = aplicar_tactico(base, defensivo, regimen_ar, red, cfg)
    if not on_rg:
        asig = {c: w for c, w in asig.items() if c != "oro"}
    motivos = (_motivo_riesgo(rg, defensivo, float(rg["defensivo"]), on_rg, regimen_ar, cfg)
               + _motivo_eventos(prox or activos, red) + _motivo_rotacion(rot, on_rot))
    campos_ev = ("nombre", "fecha", "dias_para_evento", "tipo", "reduccion_ar", "confianza", "fuente")
    return {
        "activo": on_rg or on_rot or on_ev, "aplicado": {"riesgo_global": on_rg, "rotacion": on_rot, "eventos": on_ev},
        "riesgo": rg["riesgo"], "defensivo": defensivo, "defensivo_calculado": rg["defensivo"],
        "senales": rg["senales"], "fecha_senales": rg["fecha"],
        "sectores_favorecidos": (rot or {}).get("favorecidos", []), "sectores_castigados": (rot or {}).get("castigados", []),
        "grupos": (rot or {}).get("grupos", {}), "mult_por_ticker": (rot or {}).get("mult_por_ticker", {}) if on_rot else {},
        "eventos": [{k: e.get(k) for k in campos_ev} for e in prox],
        "eventos_en_ventana": [e.get("nombre") for e in activos], "reduccion_eventos": red,
        "asignacion_base": dict(base), "asignacion": asig,
        "refugio_oro": cfg.get("refugio_oro", "GLD") if on_rg else None,
        "clases_pesos": list(cfg.get("refugio_pesos_clases") or []) if defensivo > 0 else None,
        "motivos": motivos,
    }
