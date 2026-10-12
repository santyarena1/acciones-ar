"""Parsers puros de las respuestas de las APIs públicas (data912, argentinadatos, BCRA) y de las tablas de
bonos del Reporte Semanal Gorostiaga. Sin red: reciben el JSON/texto ya descargado."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd

COLUMNAS_COTIZ = ["simbolo", "bid", "ask", "ultimo", "volumen_nominal", "operaciones", "variacion_pct"]


def _num(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # descarta NaN


def parsear_data912(filas: list[dict[str, Any]]) -> pd.DataFrame:
    """`/live/arg_bonds|arg_notes|arg_corp` -> una fila por símbolo. Precios por 100 VN; `v` es volumen nominal."""
    if not isinstance(filas, list):
        raise ValueError("data912: se esperaba una lista de cotizaciones")
    out = []
    for f in filas:
        simbolo = str(f.get("symbol") or "").strip().upper()
        if not simbolo:
            continue
        out.append({
            "simbolo": simbolo,
            "bid": _num(f.get("px_bid")),
            "ask": _num(f.get("px_ask")),
            "ultimo": _num(f.get("c")),
            "volumen_nominal": _num(f.get("v")) or 0.0,
            "operaciones": _num(f.get("q_op")) or 0.0,
            "variacion_pct": _num(f.get("pct_change")),
        })
    df = pd.DataFrame(out, columns=COLUMNAS_COTIZ)
    return df.drop_duplicates("simbolo", keep="last").set_index("simbolo")


def precio_referencia(bid: float | None, ask: float | None, ultimo: float | None) -> float | None:
    """Último operado si existe; si no, punta media; si sólo hay una punta, esa."""
    if ultimo and ultimo > 0:
        return ultimo
    puntas = [p for p in (bid, ask) if p and p > 0]
    return sum(puntas) / len(puntas) if puntas else None


def parsear_letras_argentinadatos(raw: dict[str, Any]) -> pd.DataFrame:
    """`/v1/finanzas/letras` -> ticker, precio, tea, tem, vencimiento, dias, volumen_efectivo_ars (tasas en decimal)."""
    letras = raw.get("letras") if isinstance(raw, dict) else None
    if not isinstance(letras, list):
        raise ValueError("argentinadatos: respuesta de letras sin clave 'letras'")
    out = []
    for x in letras:
        try:
            venc = date.fromisoformat(str(x["fechaVencimiento"])[:10])
        except (KeyError, ValueError):
            continue
        out.append({
            "ticker": str(x.get("ticker", "")).upper(),
            "precio": _num(x.get("precioArs")),
            "tea": (_num(x.get("teaPorcentaje")) or 0.0) / 100,
            "tem": (_num(x.get("temPorcentaje")) or 0.0) / 100,
            "vencimiento": venc,
            "dias": int(_num(x.get("diasAlVencimiento")) or 0),
            "volumen_efectivo_ars": _num(x.get("volumenEfectivoArs")) or 0.0,
        })
    return pd.DataFrame(out)


def parsear_cer_bcra(raw: dict[str, Any]) -> dict[date, float]:
    """BCRA estadísticas v4.0 `/monetarias/30` -> {fecha: CER}."""
    try:
        detalle = raw["results"][0]["detalle"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError("BCRA: respuesta de CER con formato inesperado") from e
    out = {}
    for x in detalle:
        v = _num(x.get("valor"))
        if v is not None and x.get("fecha"):
            out[date.fromisoformat(str(x["fecha"])[:10])] = v
    return out


def parsear_feriados(raw: list[dict[str, Any]]) -> set[date]:
    """argentinadatos `/v1/feriados/{anio}` -> set de fechas (incluye puentes, que BYMA no opera)."""
    return {date.fromisoformat(str(x["fecha"])[:10]) for x in raw if x.get("fecha")}


# ----------------------------------------------------------------------------- Reporte Gorostiaga

_NUM_AR = r"-?[\d\.]+,\d+"
_FILA_BONO = re.compile(
    rf"\b([A-Z][A-Z0-9]{{3,5}})\s+(\d{{1,2}}/\d{{1,2}}/\d{{4}})\s+({_NUM_AR})%\s+({_NUM_AR})\s+.*?({_NUM_AR})%\s*$")


def _a_float_ar(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def parsear_tablas_gorostiaga(texto: str) -> pd.DataFrame:
    """Filas de las tablas de bonos del reporte (figs. 7, 9 y 11): ticker, vencimiento, cupon, precio, tir (decimal).

    Toma la última cifra con % de cada fila como TIR (en la fig. 9 es TIR real, en la 11 TIR nominal).
    Sirve para validar los cálculos propios contra un tercero."""
    out = []
    for linea in texto.splitlines():
        m = _FILA_BONO.search(linea.strip())
        if not m:
            continue
        ticker, venc, cupon, precio, tir = m.groups()
        d, mth, y = (int(p) for p in venc.split("/"))
        out.append({"ticker": ticker, "vencimiento": date(y, mth, d), "cupon": _a_float_ar(cupon) / 100,
                    "precio": _a_float_ar(precio), "tir": _a_float_ar(tir) / 100})
    return pd.DataFrame(out, columns=["ticker", "vencimiento", "cupon", "precio", "tir"])
