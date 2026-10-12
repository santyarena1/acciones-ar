"""Parser puro (sin I/O) del Reporte Semanal de Mercados de Gorostiaga Bursátil.

Sub-parsers usados por `gorostiaga.parse_reporte` (texto por página de pdfplumber). Hay dos formatos conocidos:
- "completo" (~30 págs.): tabla "ADRS DE ACCIONES ARGENTINAS" y noticias "EMPRESA (TICKER) ...".
- "resumen" (~4 págs., p.ej. n°214): tabla "EMPRESA (TICKER) SEMANA 2026 RESUMEN" y
  tabla de recomendaciones "ACTIVO BANCO RECOMENDACIÓN DETALLE".
Nunca levanta excepciones: lo que no se puede leer queda en None/[] y se anota en `avisos`.
"""
from __future__ import annotations

import re
from typing import Any, Callable

MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), 1)}

FUENTES = [
    "JP Morgan", "JPMorgan", "Morgan Stanley", "Goldman Sachs", "Bank of America", "BofA", "Citi",
    "UBS", "Barclays", "HSBC", "Allaria", "BCP Securities", "Itaú", "Santander", "Bernstein",
    "Jefferies", "Deutsche Bank", "Wells Fargo", "Latin Securities", "Balanz", "BTG Pactual",
    "Credicorp", "Bradesco", "Moody's", "Fitch",
]
RATINGS = [
    "Sobreponderar", "Subponderar", "Infraponderar", "Neutral", "Comprar", "Compra", "Vender",
    "Venta", "Mantener", "Mejor Rendimiento", "Outperform", "Underperform", "Peso de mercado",
]
# Reglas de etiquetas de eventos (regex sobre el texto en minúsculas). El orden se respeta en la salida.
EVENTOS: dict[str, str] = {
    "dividendo": r"dividendo(?!s? proyectad)",
    "resultado_positivo": r"ganancia neta|utilidad neta|volvió a ganancias|\bcreció\b",
    "resultado_negativo": r"pérdida neta|\bcayó\b|deterioro|quebranto",
    "rigi": r"\brigi\b",
    "adquisicion": r"adquiri|adquisici|compraría|toma de control|tomar el control",
    "desinversion": r"desinver|vender la totalidad|cedió|\bceder\b",
    "recompra": r"recompra",
    "emision_deuda": r"obligaciones negociables|\bons?\b|colocó|colocación|emisión de deuda|bono corporativo",
    "litigio": r"litigio|fallo|demanda judicial|judicial|causa penal",
    "calificacion": r"calificaci|calificadora|moody|fitch|s&p national",
}

_NUM = r"-?\d{1,3}(?:\.\d{3})*(?:,\d+)?|-?\d+(?:,\d+)?"
_TICK = r"[A-Z][A-Z0-9]{1,5}"
_RE_RATING = re.compile(r"[“\"]\s*(" + "|".join(RATINGS) + r")\s*[”\"]")
_RE_FUENTE = re.compile("|".join(re.escape(f) for f in FUENTES))
_RE_TICKER_PAREN = re.compile(r"\((" + _TICK + r")\)")
# Siglas entre paréntesis que no son tickers
NO_TICKERS = {"DCF", "ADR", "ADRS", "PBI", "PIB", "EBITDA", "IA", "ON", "ONS", "USD", "ARS", "FMI", "BCRA",
              "INDEC", "RIGI", "GNL", "LNG", "LGN", "BESS", "OTC", "VMI", "EMAE", "MULC", "CCL", "MEP", "PO"}
_RE_HEADER = re.compile(r"^(?:(?:Resumen\s*.\s*)?Reporte Semanal de Mercados n°\d+|"
                        r"(?:Lunes|Martes)\s+\d{1,2} de \w+ de \d{4}|Página \d+)$")


def num_ar(s: str | None) -> float | None:
    """'11.403,5' -> 11403.5 ; '-3,5' -> -3.5 ; '+0,3%' -> 0.3. None si no se puede."""
    if s is None:
        return None
    t = s.strip().replace("%", "").replace("+", "").replace("$", "").replace(" ", "")
    try:
        return float(t.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def seguro(avisos: list[str], nombre: str, fn: Callable[[], Any], default: Any) -> Any:
    """Corre un sub-parser; si explota, anota el aviso y devuelve el default."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - el parser no debe romper nunca
        avisos.append(f"{nombre}: error {type(e).__name__}: {e}")
        return default


def _lineas(paginas: list[str]) -> list[str]:
    """Todas las líneas útiles, sin encabezados/pies de página repetidos."""
    out = []
    for p in paginas:
        for ln in (p or "").splitlines():
            ln = ln.strip()
            if ln and not _RE_HEADER.match(ln):
                out.append(ln)
    return out


def texto_plano(paginas: list[str]) -> str:
    return "\n".join(_lineas(paginas))


# ---------------------------------------------------------------- encabezado y macro
def parse_encabezado(primera: str) -> tuple[int | None, str | None]:
    m = re.search(r"n°\s*(\d+)", primera)
    numero = int(m.group(1)) if m else None
    f = re.search(r"(\d{1,2}) de (" + "|".join(MESES) + r") de (\d{4})", primera, re.I)
    fecha = f"{f.group(3)}-{MESES[f.group(2).lower()]:02d}-{int(f.group(1)):02d}" if f else None
    return numero, fecha


def parse_resumen(primera: str) -> str:
    """Título + primer párrafo de la página 1 (un párrafo termina en línea que cierra con '.')."""
    partes, actual = [], []
    for ln in _lineas([primera]):
        if ln.isupper():  # títulos en mayúsculas: se saltean al principio y cortan después
            if partes or actual:
                break
            continue
        actual.append(ln)
        if ln.endswith("."):
            partes.append(" ".join(actual))
            actual = []
            if len(partes) == 2:
                break
    if actual and len(partes) < 2:
        partes.append(" ".join(actual))
    texto = re.sub(r"\s+", " ", " ".join(partes)).replace("- ", "-").strip()
    if len(texto) > 1200:  # recorta en el último fin de oración antes del límite
        corte = texto.rfind(". ", 0, 1200)
        texto = texto[: corte + 1] if corte > 0 else texto[:1200]
    return texto


def parse_riesgo_pais(texto: str) -> int | None:
    for m in re.finditer(r"riesgo pa[ií]s([^.]{0,100}?)\b(\d{3,4})\s*(?:puntos|bps|pb)\b", texto, re.I):
        previo = m.group(1).lower()
        if "encima" in previo or "supera" in previo:
            continue
        return int(m.group(2))
    return None


def parse_ccl(texto: str) -> float | None:
    m = re.search(r"CCL\)?[^.]{0,120}?USDARS\s*(" + _NUM + ")", texto)
    if m:
        return num_ar(m.group(1))
    m = re.search(r"D[OÓ]LAR CCL[^\n]*\n\s*\d+\s*pb\s+\$\s*(" + _NUM + ")", texto)
    return num_ar(m.group(1)) if m else None


def parse_brecha(texto: str) -> float | None:
    m = re.search(r"brecha con la divisa[^%]{0,80}?(\d+(?:,\d+)?)\s*%", texto)
    return num_ar(m.group(1)) if m else None


# ---------------------------------------------------------------- ADRs
_RE_ADR_COMPLETO = re.compile(
    rf"^(?P<empresa>.+?)\s+(?P<ticker>{_TICK})\s+(?P<precio>{_NUM})\s+(?P<mcap>{_NUM})\s+"
    rf"(?P<s>{_NUM})\s+(?P<m>{_NUM})\s+(?P<a>{_NUM})$")
_RE_ADR_RESUMEN = re.compile(
    rf"^(?P<empresa>.+?)\s*(?:\((?P<ticker>{_TICK})\))?\s+(?P<s>[+-]?\d+(?:,\d+)?)%\s+"
    rf"(?P<a>[+-]?\d+(?:,\d+)?)%\s*(?P<resto>.*)$")


def parse_adrs_completo(paginas: list[str]) -> list[dict]:
    filas = []
    for p in paginas:
        if "ADRS DE ACCIONES ARGENTINAS" not in (p or "").upper():
            continue
        for ln in _lineas([p]):
            m = _RE_ADR_COMPLETO.match(ln)
            if m:
                filas.append({
                    "empresa": m["empresa"], "ticker": m["ticker"], "precio_usd": num_ar(m["precio"]),
                    "mcap_usd_m": num_ar(m["mcap"]), "var_semana": num_ar(m["s"]),
                    "var_mes": num_ar(m["m"]), "var_anio": num_ar(m["a"]),
                })
    return filas


def parse_adrs_resumen(texto: str) -> list[dict]:
    """Tabla del formato resumen: 'Ternium (TX) -0,1% +44,8% Comentario...' (puede partir líneas)."""
    i = texto.find("EMPRESA (TICKER)")
    if i < 0:
        return []
    filas: list[dict] = []
    for ln in texto[i:].splitlines()[1:]:
        if re.match(r"^[A-ZÁÉÍÓÚÑ ]{4,}:", ln):  # siguiente sección ("EL MUNDO: ...")
            break
        m = _RE_ADR_RESUMEN.match(ln)
        if m:
            filas.append({"empresa": m["empresa"].strip(), "ticker": m["ticker"], "precio_usd": None,
                          "mcap_usd_m": None, "var_semana": num_ar(m["s"]), "var_mes": None,
                          "var_anio": num_ar(m["a"]), "comentario": m["resto"].strip()})
        elif filas:
            t = re.match(rf"^\(({_TICK})\)\s*(.*)$", ln)
            if t and filas[-1]["ticker"] is None:
                filas[-1]["ticker"] = t.group(1)
                ln = t.group(2)
            filas[-1]["comentario"] = (filas[-1]["comentario"] + " " + ln).strip()
    return filas


# ---------------------------------------------------------------- recomendaciones
_NORMALIZA_FUENTE = {"JPMorgan": "JP Morgan", "BofA": "Bank of America"}
_RE_HORIZONTE = re.compile(r"(?:para|a|hacia)\s+((?:fines|mediados|principios) de \d{4}|(?:"
                           + "|".join(MESES) + r") de \d{4})", re.I)


def _precios_objetivo(seg: str) -> list[float]:
    k = max(seg.lower().find("objetivo"), seg.find("PO USD"))
    if k < 0:
        return []
    return [v for v in (num_ar(x) for x in re.findall(rf"USD\s*({_NUM})", seg[k:])) if v is not None]


def _asignar_precios(tickers: list[str], precios: list[float]) -> list[float | None]:
    if precios and len(tickers) == len(precios):
        return list(precios)  # patrón "USD 94 y USD 66, respectivamente"
    if precios and len(tickers) == 1:
        return [precios[-1]]  # "bajó su precio objetivo de USD 25 a USD 23" -> el último
    return [None] * len(tickers)


def _recs_oracion(oracion: str, fuente: str, ticker_default: str | None = None) -> list[dict]:
    """Cada rating entre comillas abre una cláusula; sus tickers están después (o antes si no hay)."""
    ratings = list(_RE_RATING.finditer(oracion))
    recs = []
    for i, r in enumerate(ratings):
        fin = ratings[i + 1].start() if i + 1 < len(ratings) else len(oracion)
        ini = ratings[i - 1].end() if i > 0 else 0
        despues, antes = oracion[r.end():fin], oracion[ini:r.start()]
        tickers, seg = _tickers(despues), despues
        if not tickers:
            tickers, seg = _tickers(antes), antes + despues
        if not tickers and ticker_default:
            tickers = [ticker_default]
        h = _RE_HORIZONTE.search(seg)
        for t, p in zip(tickers, _asignar_precios(tickers, _precios_objetivo(seg))):
            recs.append({"fuente": fuente, "ticker": t, "rating": r.group(1), "precio_objetivo_usd": p,
                         "horizonte": h.group(1) if h else None})
    return recs


def _tickers(seg: str) -> list[str]:
    return [t for t in dict.fromkeys(_RE_TICKER_PAREN.findall(seg)) if t not in NO_TICKERS]


def _oraciones(bloque: str) -> list[str]:
    return [o for o in re.split(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ“\"])", bloque) if o]


def _bloques(lineas: list[str]) -> list[str]:
    """Agrupa líneas en párrafos aproximados (pdfplumber no marca cortes: usamos líneas que cierran en '.')."""
    bloques, actual = [], []
    for ln in lineas:
        actual.append(ln)
        if ln.endswith(".") or ln.startswith(("Figura", "Fuente:")):
            bloques.append(" ".join(actual))
            actual = []
    if actual:
        bloques.append(" ".join(actual))
    return bloques


def parse_recomendaciones_prosa(texto: str, ticker_default: str | None = None) -> list[dict]:
    recs: list[dict] = []
    for bloque in _bloques(texto.splitlines()):
        fuente = None
        for o in _oraciones(bloque):
            f = _RE_FUENTE.search(o)
            if f:
                fuente = _NORMALIZA_FUENTE.get(f.group(0), f.group(0))
            if fuente and _RE_RATING.search(o):
                recs.extend(_recs_oracion(o, fuente, ticker_default))
    return recs


def parse_recomendaciones_tabla(texto: str) -> list[dict]:
    """Tabla del resumen: 'Petrobras (PBR) JP Morgan Sobreponderar Precio objetivo de USD 24 ...'."""
    i = texto.find("ACTIVO BANCO RECOMENDACI")
    if i < 0:
        return []
    fila = re.compile(rf"^.+?\s*\(({_TICK})\)\s+({_RE_FUENTE.pattern})\s+({'|'.join(RATINGS)})\b(.*)$")
    recs: list[dict] = []
    for ln in texto[i:].splitlines()[1:]:
        if ln.isupper():
            break
        m = fila.match(ln)
        if m:
            recs.append({"fuente": _NORMALIZA_FUENTE.get(m.group(2), m.group(2)), "ticker": m.group(1),
                         "rating": m.group(3), "precio_objetivo_usd": None, "horizonte": None, "_det": m.group(4)})
        elif recs:
            recs[-1]["_det"] += " " + ln
    for r in recs:
        precios = _precios_objetivo(r.pop("_det"))
        r["precio_objetivo_usd"] = precios[-1] if precios else None
    return recs


def recs_de_comentarios(adrs: list[dict]) -> list[dict]:
    """Comentarios de la tabla resumen: 'Goldman Sachs (Comprar, PO USD 2.300)' o prosa con comillas."""
    recs = []
    pat = re.compile(rf"({_RE_FUENTE.pattern})\s*\(({'|'.join(RATINGS)}),\s*PO USD\s*({_NUM})\)")
    for a in adrs:
        com, t = a.get("comentario") or "", a.get("ticker")
        if not t:
            continue
        for m in pat.finditer(com):
            recs.append({"fuente": _NORMALIZA_FUENTE.get(m.group(1), m.group(1)), "ticker": t,
                         "rating": m.group(2), "precio_objetivo_usd": num_ar(m.group(3)), "horizonte": None})
        recs.extend(parse_recomendaciones_prosa(pat.sub("", com), ticker_default=t))
    return recs


def dedup_recs(recs: list[dict]) -> list[dict]:
    vistos, out = set(), []
    for r in recs:
        k = (r["fuente"], r["ticker"], r["rating"], r["precio_objetivo_usd"])
        if k not in vistos:
            vistos.add(k)
            out.append(r)
    return out


# ---------------------------------------------------------------- noticias
_RE_NOTICIA = re.compile(rf"^(?P<emp>[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ0-9&.,'’ -]*[A-ZÁÉÍÓÚÑÜ0-9.])"
                         rf"(?:\s*\((?P<t>{_TICK})\)\s*:?)?\s+(?P<resto>.*)$")
_CORTE_PARRAFO = tuple(FUENTES) + ("Las ", "Los ", "Estas ", "Argentina y ")


def etiquetar_eventos(texto: str) -> list[str]:
    t = texto.lower()
    return [k for k, pat in EVENTOS.items() if re.search(pat, t)]


def _inicio_noticia(ln: str, previa: str) -> tuple[str, str | None] | None:
    if previa.startswith("Figura") or not (previa.endswith((".", ":")) or previa.startswith("Fuente")):
        return None
    m = _RE_NOTICIA.match(ln)
    if not m or not re.search(r"[A-ZÁÉÍÓÚÑ]{3,}", m["emp"]):
        return None
    resto, t = m["resto"], m["t"]
    if t is None and (not resto[:1].islower() or len(m["emp"]) < 6):
        return None
    if t is not None and resto[:1].isdigit():
        return None  # epígrafe de gráfico: "YPF (YPF): 5 años, en dólares"
    return m["emp"].strip(" ,.-"), t


def _seccion_acciones(lineas: list[str]) -> list[str]:
    # "Renta Variable" en minúsculas = título de sección (el índice de la pág. 2 va en mayúsculas)
    ini = next((i for i, ln in enumerate(lineas) if "Renta Variable" in ln), 0)
    fin = next((i for i, ln in enumerate(lineas) if i > ini and ln == "MERCADOS INTERNACIONALES"), len(lineas))
    return lineas[ini:fin]


def parse_noticias(lineas: list[str]) -> list[dict]:
    noticias: list[dict] = []
    actual: dict | None = None
    previa = "."
    for ln in _seccion_acciones(lineas):
        inicio = _inicio_noticia(ln, previa)
        corta = ln.startswith(("Figura", "Fuente:")) or ln.isupper() or (
            previa.endswith(".") and ln.startswith(_CORTE_PARRAFO))
        if inicio or corta:
            actual = None
        if inicio:
            actual = {"ticker": inicio[1], "empresa": inicio[0], "texto": ln}
            noticias.append(actual)
        elif actual is not None:
            actual["texto"] += " " + ln
        previa = ln
    return _cerrar_noticias(noticias)


def _cerrar_noticias(noticias: list[dict]) -> list[dict]:
    out, vistos = [], set()
    for n in noticias:
        texto = re.sub(r"\s+", " ", n["texto"]).strip()[:2000]
        if texto in vistos:
            continue  # el PDF a veces repite párrafos
        vistos.add(texto)
        out.append({**n, "texto": texto, "eventos": etiquetar_eventos(texto)})
    return out


def noticias_de_comentarios(adrs: list[dict]) -> list[dict]:
    """Formato resumen: el comentario de cada ADR es la noticia (salvo 'Sin novedades')."""
    out = []
    for a in adrs:
        com = (a.get("comentario") or "").strip()
        if com and not com.lower().startswith("sin novedades"):
            out.append({"ticker": a.get("ticker"), "empresa": a.get("empresa"), "texto": com,
                        "eventos": etiquetar_eventos(com)})
    return out
