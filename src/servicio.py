"""Corrida completa: datos -> macro -> scores -> asignación por clase -> objetivos -> órdenes -> guía.

Lo usan la CLI (main.py), la app web (app/) y la tarea semanal. Nunca envía órdenes: solo las sugiere.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from .analysis.macro import asignacion_clases, regimen_macro
from .analysis.tactico import consolidar_minimos, resolver_tactico
from .config import sector_map, tipo_map
from .broker.iol import tz_argentina
from .guia import generar_guia
from .pipeline import analyze, load_prices
from .portfolio.equiponderado import objetivos_equiponderados
from .portfolio.escala import asequible, escalar
from .portfolio.renta_fija_alloc import objetivo_estacionamiento, CLASES_RF, objetivos_renta_fija
from .portfolio.rules import CLASE_DE_TIPO, build_targets, generate_orders
from .store import Corrida, guardar

CLASE_RF_A_CARTERA = {c: cartera for cartera, clases in CLASES_RF.items() for c in clases}
TIPO_A_CLASE = {**CLASE_DE_TIPO, "letra": "pesos", "bono": "bonos_usd", "on": "bonos_usd"}


def crear_broker(nombre: str, settings: dict):
    if nombre == "iol":
        from .broker.iol import IOLBroker, IOLClient
        cfg = settings.get("iol") or {}
        cliente = IOLClient(max_reintentos=cfg.get("max_reintentos", 3),
                            backoff_base=cfg.get("backoff_base_seg", 1.0),
                            intervalo_min=cfg.get("intervalo_min_seg", 0.25))
        return IOLBroker(cliente, settings)
    from .broker.paper import PaperBroker
    return PaperBroker(settings["portfolio"]["paper_capital_inicial_ars"],
                       comision=(settings.get("paper") or {}).get("comision", 0.006))


def _reporte_semanal(universe: list[dict], settings: dict) -> tuple[dict, dict | None]:
    """(contexto por ticker, macro del último reporte). Si algo falla, sigue sin reporte."""
    try:
        from .data import gorostiaga as g
        try:
            g.actualizar()
        except Exception as e:
            print(f"  [aviso] no pude bajar reportes nuevos de Gorostiaga: {e}")
        reportes = g.cargar_historial()
        if not reportes:
            return {}, None
        semanas = settings.get("alertas", {}).get("semanas_contexto", 4)
        return g.contexto_por_ticker(reportes, universe, semanas), g.macro_ultimo(reportes)
    except ImportError:
        return {}, None
    except Exception as e:
        print(f"  [aviso] reporte semanal no disponible: {e}")
        return {}, None


def _renta_fija() -> pd.DataFrame:
    """Bonos y letras indexados por el símbolo que se opera en pesos en IOL (cotizan cada 100 VN)."""
    try:
        from .renta_fija import cargar_renta_fija
        rf = cargar_renta_fija()
        if rf is None or rf.empty:
            return pd.DataFrame()
        rf = rf.copy()
        rf["ticker_iol"] = rf["ticker_iol"].fillna(rf["ticker"])
        rf = rf.drop_duplicates("ticker_iol").set_index("ticker_iol")
        rf["mult"] = 0.01
        return rf
    except ImportError:
        return pd.DataFrame()
    except Exception as e:
        print(f"  [aviso] renta fija no disponible: {e}")
        return pd.DataFrame()


def _serie_segura(fn, desde: date) -> pd.Series | None:
    try:
        return fn(desde)
    except Exception as e:
        print(f"  [aviso] {fn.__name__}: {e}")
        return None


def _macro(precios, settings: dict) -> dict:
    from .data.prices import load_oficial, load_riesgo_pais
    desde = date.today() - timedelta(days=400)
    return regimen_macro(_serie_segura(load_riesgo_pais, desde), precios.ccl,
                         _serie_segura(load_oficial, desde), precios.merval_usd, settings)


def _clase_de(t: str, tipos: dict, rf: pd.DataFrame, pos: dict) -> str:
    if not rf.empty and t in rf.index:
        return CLASE_RF_A_CARTERA.get(rf.at[t, "clase"], "bonos_usd")
    return TIPO_A_CLASE.get(tipos.get(t) or pos.get("tipo", "accion"), "acciones_ar")


def _ultimo_ccl(precios) -> float | None:
    ccl = getattr(precios, "ccl", None)
    if ccl is None or ccl.dropna().empty:
        return None
    return float(ccl.dropna().iloc[-1])


def _precio_posicion(t: str, p: dict, ccl: float | None) -> float | None:
    """Precio en PESOS de una posición del broker. Las líneas en dólares (ONs/bonos D) se pasan con el CCL;
    si la unidad del precio es dudosa (por unidad vs. cada 100 VN) no se valúa: mejor 0 que x100."""
    precio = p.get("precio")
    if not precio:
        return None
    if p.get("unidad_dudosa"):
        print(f"  [aviso] {t}: unidad de precio dudosa en el broker; no se valúa ni se opera")
        return None
    if str(p.get("moneda", "ARS")).upper() == "USD":
        if not ccl:
            print(f"  [aviso] {t}: posición en dólares y sin CCL para pasarla a pesos; no se valúa")
            return None
        return float(precio) * ccl
    return float(precio)


def _precios_y_mult(precios, rf: pd.DataFrame, posiciones: dict) -> tuple[dict, dict]:
    ccl = _ultimo_ccl(precios)
    px = {t: v for t, p in posiciones.items() if (v := _precio_posicion(t, p, ccl))}
    px.update(precios.ultimo_ars)
    mult = {}
    if not rf.empty and "precio_ars" in rf.columns:
        for t, f in rf.iterrows():
            if pd.notna(f["precio_ars"]):
                px[t] = float(f["precio_ars"])
                mult[t] = float(f.get("mult", 0.01) if pd.notna(f.get("mult", 0.01)) else 0.01)
    for t, p in posiciones.items():
        if p.get("tipo") in ("bono", "letra", "on"):
            mult.setdefault(t, 0.01)
    return px, mult


def _estrategia_ar(settings: dict) -> str:
    return str((settings.get("estrategia") or {}).get("acciones_ar", "score"))


def _targets_rv(ranking: pd.DataFrame, pesos_rv: dict, sectores: dict, settings: dict, asignacion: dict,
                tipos: dict, clases: dict | None = None, valor_total: float = 0.0) -> dict[str, float]:
    """Renta variable. Con estrategia.acciones_ar = equiponderado: locales parejas por liquidez (panel líder) y
    CEDEARs por score (con su parte proporcional del máximo de posiciones). Si no, todo por score."""
    presup = {c: asignacion.get(c, 0.0) for c in ("acciones_ar", "cedears")}
    if _estrategia_ar(settings) != "equiponderado":
        return build_targets(ranking, pesos_rv, sectores, settings, presupuestos=presup, tipos=tipos)
    clases = clases or {}
    es_ar = lambda t: clases.get(t) == "acciones_ar" or tipos.get(t) == "accion"  # noqa: E731
    p = settings["portfolio"]
    tot, max_pos = sum(presup.values()), p.get("max_posiciones_rv")
    tope = p.get("max_posiciones_cedears")
    if tope is None:
        tope = round(max_pos * presup["cedears"] / tot) if max_pos and tot else max_pos
    s_ced = {**settings, "portfolio": {**p, "max_posiciones_rv": tope}}
    ced = ranking[ranking["tipo"] == "cedear"]
    if valor_total and tope:
        # con poco capital: solo CEDEARs cuya unidad entra en el tamaño de posición (o que ya tenemos)
        tam = valor_total * presup["cedears"] / tope
        ced = ced[[asequible(ced.at[t, "precio_ars"], tam) or pesos_rv.get(t, 0) > 0 for t in ced.index]]
    out = build_targets(ced, {t: w for t, w in pesos_rv.items() if not es_ar(t)}, sectores, s_ced,
                        presupuestos={"cedears": presup["cedears"]}, tipos=tipos)
    out.update(objetivos_equiponderados(ranking, {t: w for t, w in pesos_rv.items() if es_ar(t)},
                                        presup["acciones_ar"], settings))
    return out


def _lotes(rf: pd.DataFrame) -> dict[str, int]:
    """Lámina mínima de bonos/ONs si renta fija la informa (`lamina_minima`); si no, 1."""
    if rf.empty or "lamina_minima" not in rf.columns:
        return {}
    return {t: int(v) for t, v in rf["lamina_minima"].items() if pd.notna(v) and v >= 1}


def correr(horizonte: str, perfil: str, broker_nombre: str, settings: dict, universe: list[dict],
           guardar_corrida: bool = True, broker=None) -> Corrida:
    broker = broker or crear_broker(broker_nombre, settings)
    posiciones, caja = broker.get_positions(), broker.get_cash_ars()
    print("Bajando reporte semanal...")
    contexto, reporte = _reporte_semanal(universe, settings)
    print("Bajando precios, CCL y macro...")
    precios = load_prices(universe, settings)
    macro = _macro(precios, settings)
    asignacion = asignacion_clases(perfil, macro["regimen"], settings)
    tactico = _tactico(asignacion, macro, universe, settings)
    asignacion = tactico.get("asignacion", asignacion)
    print("Bajando fundamentales...")
    from .data.fundamentals import load_fundamentals
    fund = load_fundamentals(universe, limites=(settings.get("fundamental") or {}).get("limites"))
    ranking = analyze(precios.usd, fund, universe, settings, horizonte, set(posiciones),
                      precios.vol_ars, contexto, precios.ultimo_ars, precios.calidad)
    print("Analizando renta fija...")
    rf = _renta_fija()
    return _armar(horizonte, perfil, broker.nombre, settings, universe, posiciones, caja, precios, macro,
                  asignacion, ranking, rf, contexto, reporte, guardar_corrida, tactico)


def _tactico(asignacion: dict, macro: dict, universe: list[dict], settings: dict) -> dict:
    """Capa táctica (riesgo global, rotación, eventos). Si falla, sigue con la asignación de siempre."""
    try:
        from .config import load_eventos
        from .data.mercado_global import series_tacticas
        from .pipeline import _ahora_ar, _hora
        print("Bajando datos del mercado global (riesgo, sectores)...")
        hora = _hora((settings.get("datos") or {}).get("hora_ruedas_cerradas", "18:00"))
        series = series_tacticas(settings, _ahora_ar(), hora)
        ced = {a["ticker"]: a["sector"] for a in universe if a["tipo"] == "cedear"}
        return resolver_tactico(asignacion, macro.get("regimen", "sin datos"), series, ced, load_eventos(),
                                date.today(), settings)
    except Exception as e:
        print(f"  [aviso] capa táctica no disponible: {e}")
        return {}


def _aplicar_tactico_cartera(tactico: dict, asignacion: dict, total: float, ranking: pd.DataFrame, clases: dict,
                             settings: dict) -> tuple[dict, dict, pd.DataFrame, dict, dict, str | None]:
    """Lo que la capa táctica cambia en la cartera: oro chico se suma a pesos, el CEDEAR de oro pasa a ser refugio
    (no se elige por score), multiplicadores de rotación y pesos solo en letras cortas si hay modo defensivo."""
    if not tactico:
        return tactico, asignacion, ranking, clases, settings, None
    oro = tactico.get("refugio_oro")
    if oro:
        asignacion = consolidar_minimos(asignacion, total, float(settings["portfolio"].get("posicion_minima_ars") or 0))
        clases = {**clases, oro: "oro"}
    if tactico.get("mult_por_ticker"):
        ranking = ranking.assign(mult_rotacion=[tactico["mult_por_ticker"].get(t, 1.0) for t in ranking.index])
    if tactico.get("clases_pesos"):
        settings = {**settings, "renta_fija": {**(settings.get("renta_fija") or {}),
                                               "clases_pesos": tactico["clases_pesos"]}}
    return {**tactico, "asignacion": asignacion}, asignacion, ranking, clases, settings, oro


def _objetivo_oro(oro: str | None, asignacion: dict, ranking: pd.DataFrame, pesos_act: dict) -> dict[str, float]:
    """Peso del CEDEAR de oro = clase 'oro'. Con datos rotos no se toca (se mantiene lo que hay)."""
    if not oro:
        return {}
    roto = oro not in ranking.index or str(ranking.at[oro, "calidad_datos"] if "calidad_datos" in ranking.columns
                                             else "").strip() != ""
    return {oro: pesos_act.get(oro, 0.0) if roto else float(asignacion.get("oro", 0.0))}


def _armar(horizonte, perfil, broker_nombre, settings, universe, posiciones, caja, precios, macro, asignacion,
           ranking, rf, contexto, reporte, guardar_corrida, tactico=None) -> Corrida:
    tipos = tipo_map(universe)
    px, mult = _precios_y_mult(precios, rf, posiciones)
    valores = {t: p["cantidad"] * px.get(t, 0) * mult.get(t, 1.0) for t, p in posiciones.items()}
    total = caja + sum(valores.values())
    pesos_act = {t: v / total for t, v in valores.items()} if total else {}
    clases = {t: _clase_de(t, tipos, rf, posiciones.get(t, {})) for t in set(pesos_act) | set(ranking.index)}
    tactico, asignacion, ranking_rv, clases, settings, oro = _aplicar_tactico_cartera(
        tactico or {}, asignacion, total, ranking, clases, settings)
    ranking_rv = ranking_rv.drop(index=[oro], errors="ignore") if oro else ranking_rv
    pesos_rv = {t: w for t, w in pesos_act.items() if clases[t] in ("acciones_ar", "cedears")}
    settings, escala = escalar(settings, total, asignacion)   # cuántas posiciones entran con este capital
    targets = _targets_rv(ranking_rv, pesos_rv, sector_map(universe), settings, asignacion, tipos, clases, total)
    targets.update(_objetivo_oro(oro, asignacion, ranking, pesos_act))
    targets.update(objetivos_renta_fija(rf, asignacion, pesos_act, settings))
    targets.update(objetivo_estacionamiento(targets, rf, total, settings))   # efectivo sobrante -> Lecap corta
    ordenes = generate_orders(targets, posiciones, caja, px, settings, precios.vol_ars, mult, _lotes(rf))
    actual_clase = {"caja": caja / total if total else 1.0}
    for t, w in pesos_act.items():
        actual_clase[clases.get(t, "acciones_ar")] = actual_clase.get(clases.get(t, "acciones_ar"), 0) + w
    objetivos = pd.DataFrame({"clase": {t: clases.get(t, _clase_de(t, tipos, rf, {})) for t in targets},
                              "peso_objetivo": targets,
                              "peso_actual": {t: pesos_act.get(t, 0.0) for t in targets}})
    guia = generar_guia(macro, asignacion, actual_clase, perfil, ranking, ordenes, rf if not rf.empty else None, reporte,
                        estrategia_ar=_estrategia_ar(settings), tactico=tactico)
    ahora = datetime.now(tz_argentina())          # el runner de la nube está en UTC: todo en hora Argentina
    meta = {"fecha": ahora.isoformat(timespec="minutes"), "horizonte": horizonte, "perfil": perfil,
            "broker": broker_nombre, "macro": macro, "asignacion": asignacion, "actual_por_clase": actual_clase,
            "cartera": {"caja": caja, "valor_total": total, "posiciones": posiciones},
            "reporte_semanal": reporte, "contexto": contexto, "escala": escala, "tactico": tactico or None}
    c = Corrida(ahora.strftime("%Y%m%d_%H%M"), meta, ranking, rf, objetivos, ordenes, guia)
    if guardar_corrida:
        guardar(c)
    return c
