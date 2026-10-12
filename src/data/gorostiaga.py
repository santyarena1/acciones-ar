"""Reporte Semanal de Mercados de Gorostiaga Bursátil: descarga, parseo y contexto por ticker.

Se publica un PDF por semana en https://gorostiagabursatil.com/reportes/S{n}.pdf (lunes a la noche o
martes); solo quedan públicos los últimos ~3, así que el historial se arma acá.

Los PDFs NUNCA se guardan (pedido del dueño): se baja -> se parsea -> se persiste TODO lo extraído (numero, fecha,
formato, resumen, url, macro, adrs, recomendaciones, noticias con eventos, tablas de bonos, avisos) -> se borra el
PDF enseguida, también si el parseo falla (queda una nota en `avisos`). Con DATABASE_URL va a la tabla `reportes`;
sin base, a data/reportes/S{n}.json. "No volver a bajar" se decide por el registro guardado, nunca por el PDF.
`parse_reporte` es puro (sin I/O); los sub-parsers viven en `gorostiaga_parse.py`.

Uso típico:
    reportes = cargar_historial()            # o actualizar() para bajar lo nuevo
    ctx = contexto_por_ticker(reportes, load_universe())
    macro = macro_ultimo(reportes)
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

import requests

from ..config import DATA_DIR
from .gorostiaga_parse import (
    dedup_recs, recs_de_comentarios, seguro, texto_plano, noticias_de_comentarios, parse_adrs_completo,
    parse_adrs_resumen, parse_brecha, parse_ccl, parse_encabezado, parse_noticias,
    parse_recomendaciones_prosa, parse_recomendaciones_tabla, parse_resumen, parse_riesgo_pais,
)

__all__ = ["parse_reporte", "numero_esperado", "descargar", "extraer_paginas", "actualizar",
           "cargar_historial", "contexto_por_ticker", "macro_ultimo"]

log = logging.getLogger(__name__)

URL = "https://gorostiagabursatil.com/reportes/S{n}.pdf"
DIR_REPORTES = DATA_DIR / "reportes"
NUMERO_REF, FECHA_REF = 212, date(2026, 9, 21)  # n°212 = lunes 21/09/2026, +1 por semana
TIMEOUT_S = 30
HEADERS = {"User-Agent": "Mozilla/5.0 (acciones-ar; analizador personal de portfolio)"}
SONDEO_ATRAS, SONDEO_ADELANTE = 3, 1  # números a probar alrededor del esperado


# ---------------------------------------------------------------- parseo (puro)
def _parse_secciones(paginas: list[str], texto: str, es_resumen: bool, avisos: list[str]) -> tuple:
    if es_resumen:
        adrs = seguro(avisos, "adrs", lambda: parse_adrs_resumen(texto), [])
        noticias = seguro(avisos, "noticias", lambda: noticias_de_comentarios(adrs), [])
        recs = seguro(avisos, "recomendaciones",
                       lambda: parse_recomendaciones_tabla(texto) + recs_de_comentarios(adrs), [])
    else:
        adrs = seguro(avisos, "adrs", lambda: parse_adrs_completo(paginas), [])
        noticias = seguro(avisos, "noticias", lambda: parse_noticias(texto.splitlines()), [])
        recs = seguro(avisos, "recomendaciones", lambda: parse_recomendaciones_prosa(texto), [])
    return adrs, noticias, dedup_recs(recs)


def parse_reporte(paginas: list[str]) -> dict:
    """Parsea el texto por página de un reporte. Nunca levanta: lo que falla queda en `avisos`."""
    avisos: list[str] = []
    paginas = [p or "" for p in (paginas or []) if isinstance(p, str) or p is None]
    primera = paginas[0] if paginas else ""
    texto = seguro(avisos, "texto", lambda: texto_plano(paginas), "")
    numero, fecha = seguro(avisos, "encabezado", lambda: parse_encabezado(primera), (None, None))
    es_resumen = "EMPRESA (TICKER)" in texto or primera.lstrip().startswith("Resumen")
    adrs, noticias, recs = _parse_secciones(paginas, texto, es_resumen, avisos)
    rep = {
        "numero": numero, "fecha": fecha, "formato": "resumen" if es_resumen else "completo",
        "resumen": seguro(avisos, "resumen", lambda: parse_resumen(primera), ""),
        "riesgo_pais": seguro(avisos, "riesgo_pais", lambda: parse_riesgo_pais(texto), None),
        "ccl": seguro(avisos, "ccl", lambda: parse_ccl(texto), None),
        "brecha_pct": seguro(avisos, "brecha_pct", lambda: parse_brecha(texto), None),
        "adrs": adrs, "recomendaciones": recs, "noticias": noticias, "avisos": avisos,
    }
    for campo in ("numero", "fecha", "riesgo_pais", "ccl", "brecha_pct"):
        if rep[campo] is None:
            avisos.append(f"{campo}: no encontrado")
    for campo in ("adrs", "recomendaciones", "noticias"):
        if not rep[campo]:
            avisos.append(f"{campo}: vacío")
    return rep


# ---------------------------------------------------------------- numeración
def numero_esperado(fecha: date) -> int:
    """Número del reporte del lunes de esa semana (o del lunes anterior)."""
    return NUMERO_REF + (fecha - FECHA_REF).days // 7


def fecha_de_numero(n: int) -> date:
    return FECHA_REF + timedelta(weeks=n - NUMERO_REF)


# ---------------------------------------------------------------- I/O
def descargar(n: int, destino_dir: Path, session: requests.Session | None = None) -> Path | None:
    """Baja S{n}.pdf a destino_dir. None si no existe (404), si falla la red o si no es un PDF."""
    url = URL.format(n=n)
    try:
        resp = (session or requests).get(url, timeout=TIMEOUT_S, headers=HEADERS)
    except requests.RequestException as e:
        log.warning("No pude bajar el reporte %s: %s", n, e)
        return None
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        log.warning("Reporte %s: HTTP %s", n, resp.status_code)
        return None
    if not resp.content.startswith(b"%PDF"):
        log.warning("Reporte %s: la respuesta no es un PDF", n)
        return None
    destino_dir.mkdir(parents=True, exist_ok=True)
    path = destino_dir / f"S{n}.pdf"
    path.write_bytes(resp.content)
    return path


def extraer_paginas(pdf: Path) -> list[str]:
    """Texto por página con pdfplumber. [] si el PDF no se puede leer."""
    try:
        import pdfplumber  # import diferido: solo hace falta para leer PDFs nuevos
        with pdfplumber.open(pdf) as doc:
            return [p.extract_text() or "" for p in doc.pages]
    except Exception as e:  # noqa: BLE001 - PDF corrupto o pdfplumber ausente
        log.warning("No pude leer %s: %s", pdf, e)
        return []


def _guardar_json(rep: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def _tablas_bonos(paginas: list[str], avisos: list[str]) -> list[dict]:
    """Tablas de bonos del reporte (ticker, vencimiento, cupón, precio, TIR) para validar la valuación propia."""
    try:
        from ..renta_fija.parsers import parsear_tablas_gorostiaga
        df = parsear_tablas_gorostiaga("\n".join(paginas))
        return [{**f, "vencimiento": f["vencimiento"].isoformat()} for f in df.to_dict(orient="records")]
    except Exception as e:  # noqa: BLE001 - una tabla rara no tira abajo el resto del reporte
        avisos.append(f"tablas_bonos: {type(e).__name__}")
        return []


def _registro(pdf: Path, n: int) -> dict:
    """Todo lo que se extrae del PDF. Nunca levanta: si falla, devuelve un registro mínimo con el aviso."""
    try:
        paginas = extraer_paginas(pdf)
        rep = parse_reporte(paginas)
        if not paginas:
            rep["avisos"].append("pdf: no se pudo leer el texto")
        rep["tablas_bonos"] = _tablas_bonos(paginas, rep["avisos"])
    except Exception as e:  # noqa: BLE001
        rep = {"numero": n, "fecha": None, "avisos": [f"parseo: falló ({type(e).__name__})"]}
    rep["numero"] = rep.get("numero") or n
    rep["url"] = URL.format(n=n)
    return rep


def _procesar_pdf(pdf: Path, n: int, guardar) -> dict:
    """Parsea, persiste con `guardar(rep)` y borra el PDF siempre (éxito o falla)."""
    try:
        rep = _registro(pdf, n)
        guardar(rep)
        return rep
    finally:
        pdf.unlink(missing_ok=True)


def _limpiar_pdfs(dir: Path) -> None:
    """Borra PDFs viejos de data/reportes/ que ya tienen su JSON (antes se guardaban)."""
    for pdf in Path(dir).glob("S*.pdf"):
        if pdf.with_suffix(".json").exists():
            pdf.unlink(missing_ok=True)


def _usa_db(dir: Path | None) -> bool:
    from .. import db
    return dir is None and db.hay_db()


def _fecha(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def _actualizar_db(hoy: date | None, session: requests.Session | None) -> list[dict]:
    import tempfile

    from .. import db
    from ..store import limpiar_json
    esperado = numero_esperado(hoy or date.today())
    guardados, nuevos = db.numeros_reportes(), []
    with tempfile.TemporaryDirectory(prefix="reportes_") as tmp:
        for n in range(esperado - SONDEO_ATRAS, esperado + SONDEO_ADELANTE + 1):
            if n in guardados:
                continue
            pdf = descargar(n, Path(tmp), session)
            if pdf is None:
                continue
            rep = _procesar_pdf(pdf, n, lambda r: db.guardar_reporte(n, _fecha(r.get("fecha")), limpiar_json(r)))
            nuevos.append(limpiar_json(rep))
            log.info("Reporte semanal n°%s procesado", n)
    return nuevos


def actualizar(dir: Path | None = None, hoy: date | None = None,
               session: requests.Session | None = None) -> list[dict]:
    """Baja y parsea los reportes que falten alrededor del número esperado para hoy.

    No vuelve a bajar lo que ya está (en archivos: si falta solo el JSON, lo regenera). Devuelve los reportes
    nuevos de esta corrida, ordenados por número. Pasar `dir` fuerza archivos.
    """
    if _usa_db(dir):
        return _actualizar_db(hoy, session)
    dir = Path(dir or DIR_REPORTES)
    _limpiar_pdfs(dir)
    esperado = numero_esperado(hoy or date.today())
    nuevos = []
    for n in range(esperado - SONDEO_ATRAS, esperado + SONDEO_ADELANTE + 1):
        pdf, js = dir / f"S{n}.pdf", dir / f"S{n}.json"
        if js.exists():
            continue
        if not pdf.exists() and descargar(n, dir, session) is None:   # un PDF suelto (corte previo) se procesa
            continue
        nuevos.append(_procesar_pdf(pdf, n, lambda r, js=js: _guardar_json(r, js)))
        log.info("Reporte Gorostiaga n°%s procesado", n)
    return nuevos


def cargar_historial(dir: Path | None = None) -> list[dict]:
    """Todos los reportes guardados, ordenados por número (en archivos, los ilegibles se saltean con aviso)."""
    if _usa_db(dir):
        from .. import db
        return [r for r in db.cargar_reportes() if isinstance(r, dict)]
    reportes = []
    for js in Path(dir or DIR_REPORTES).glob("S*.json"):
        try:
            reportes.append(json.loads(js.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Salteo %s: %s", js, e)
    return sorted(reportes, key=lambda r: r.get("numero") or 0)


# ---------------------------------------------------------------- contexto
def _mapa_tickers(universe: list[dict]) -> dict[str, str]:
    """Ticker del reporte (local o ADR) -> ticker local del universo."""
    mapa: dict[str, str] = {}
    for a in universe:
        local = a.get("ticker")
        if not local:
            continue
        mapa[local] = local
        if a.get("adr"):
            mapa.setdefault(a["adr"], local)
    return mapa


def _ultimas(reportes: list[dict], semanas: int) -> list[dict]:
    """Los últimos `semanas` reportes, del más nuevo al más viejo."""
    orden = sorted(reportes, key=lambda r: r.get("numero") or 0, reverse=True)
    if not orden:
        return []
    tope = (orden[0].get("numero") or 0) - semanas
    return [r for r in orden if (r.get("numero") or 0) > tope]


def _adr_mas_reciente(reportes: list[dict], simbolos: set[str], campo: str) -> float | None:
    for r in reportes:  # ya vienen del más nuevo al más viejo
        for a in r.get("adrs") or []:
            if a.get("ticker") in simbolos and a.get(campo) is not None:
                return a[campo]
    return None


def _upside(recs: list[dict], precio: float | None) -> float | None:
    objetivos = [r["precio_objetivo_usd"] for r in recs if r.get("precio_objetivo_usd")]
    if not precio or not objetivos:
        return None
    return round(mean(o / precio - 1 for o in objetivos), 4)


def _recs_unicas(recs: list[dict]) -> list[dict]:
    """Una recomendación por fuente: la más reciente (recs ya vienen de nuevo a viejo)."""
    vistas, out = set(), []
    for r in recs:
        if r.get("fuente") not in vistas:
            vistas.add(r.get("fuente"))
            out.append(r)
    return out


def _acumular(recientes: list[dict], mapa: dict[str, str]) -> dict[str, dict]:
    ctx: dict[str, dict] = {}
    for rep in recientes:
        meta = {"numero": rep.get("numero"), "fecha": rep.get("fecha")}
        for n in rep.get("noticias") or []:
            local = mapa.get(n.get("ticker") or "")
            if local:
                ctx.setdefault(local, {"noticias": [], "recomendaciones": []})["noticias"].append(
                    {**meta, "texto": n.get("texto", ""), "eventos": n.get("eventos") or []})
        for r in rep.get("recomendaciones") or []:
            local = mapa.get(r.get("ticker") or "")
            if local:
                ctx.setdefault(local, {"noticias": [], "recomendaciones": []})["recomendaciones"].append(
                    {**meta, **r})
    return ctx


def contexto_por_ticker(reportes: list[dict], universe: list[dict], semanas: int = 4) -> dict[str, dict]:
    """Noticias, eventos y recomendaciones de las últimas `semanas` por ticker local del universo.

    upside_consenso = promedio de (precio objetivo / último precio del ADR - 1), una rec por fuente.
    """
    mapa = _mapa_tickers(universe)
    recientes = _ultimas(reportes, semanas)
    ctx = _acumular(recientes, mapa)
    simbolos_por_local: dict[str, set[str]] = {}
    for simbolo, local in mapa.items():
        simbolos_por_local.setdefault(local, set()).add(simbolo)
    # los que figuran en la tabla de ADRs del último reporte entran aunque no tengan noticias
    for a in (recientes[0].get("adrs") or []) if recientes else []:
        if a.get("ticker") in mapa:
            ctx.setdefault(mapa[a["ticker"]], {"noticias": [], "recomendaciones": []})
    for local, c in ctx.items():
        simbolos = simbolos_por_local.get(local, {local})
        recs = _recs_unicas(c["recomendaciones"])
        c["recomendaciones"] = recs
        c["eventos"] = sorted({e for n in c["noticias"] for e in n["eventos"]})
        c["upside_consenso"] = _upside(recs, _adr_mas_reciente(recientes, simbolos, "precio_usd"))
        c["var_semana_adr"] = _adr_mas_reciente(recientes[:1], simbolos, "var_semana")
    return ctx


def macro_ultimo(reportes: list[dict]) -> dict:
    """Último dato macro disponible. Si el reporte más nuevo no trae un campo (p.ej. el formato
    resumen no publica la brecha), se toma del reporte anterior más cercano que sí lo tenga."""
    orden = sorted(reportes, key=lambda r: r.get("numero") or 0, reverse=True)
    if not orden:
        return {"numero": None, "fecha": None, "resumen": "", "riesgo_pais": None, "ccl": None,
                "brecha_pct": None}
    out = {k: orden[0].get(k) for k in ("numero", "fecha", "resumen")}
    for campo in ("riesgo_pais", "ccl", "brecha_pct"):
        out[campo] = next((r[campo] for r in orden if r.get(campo) is not None), None)
    return out
