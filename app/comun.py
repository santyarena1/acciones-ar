"""Piezas compartidas de la app: estilos, datos del último análisis, estado del operador y formatos."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.etiquetas import CLASE_RF, TIPO, nombre  # noqa: E402
from src import store  # noqa: E402
from src.config import load_settings, load_universe  # noqa: E402

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,700&family=Inter:wght@400;500;600&display=swap');
:root { --tinta:#1C1B19; --papel:#F6F2EA; --papel2:#ECE5D8; --verde:#1F5C4A; --rojo:#A33B2B;
        --ambar:#B7791F; --gris:#6B675F; --linea:#D8CFBF; }
html, body, [class*="css"], .stMarkdown { font-family: 'Inter', sans-serif; }
h1, h2, h3 { font-family: 'Fraunces', serif !important; letter-spacing: -0.01em; color: var(--tinta); }
h1 { font-size: 2.3rem !important; font-weight: 700 !important; }
[data-testid="stAppViewContainer"], [data-testid="stHeader"] { background: var(--papel); }
.block-container { padding-top: 2rem; max-width: 1200px; }
.kicker { text-transform: uppercase; letter-spacing: .14em; font-size: .72rem; color: var(--gris); font-weight: 600; }
.tarjeta { background: #FFFDF8; border: 1px solid var(--linea); border-radius: 4px 14px 4px 14px;
           padding: 1rem 1.2rem; box-shadow: 0 1px 0 var(--linea), 0 10px 24px -18px rgba(28,27,25,.35);
           transition: transform .18s ease, box-shadow .18s ease; height: 100%; }
.tarjeta:hover { transform: translateY(-2px); box-shadow: 0 1px 0 var(--linea), 0 16px 30px -18px rgba(28,27,25,.45); }
.tarjeta, .tarjeta * { color: var(--tinta); }
.tarjeta .kicker, .tarjeta .sub { color: var(--gris); }
.cifra { font-family: 'Fraunces', serif; font-size: clamp(1.15rem, 1.8vw, 1.9rem); font-weight: 700; line-height: 1.15;
         white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin: .2rem 0; }
.sub { color: var(--gris); font-size: .85rem; }
.tarjeta .verde, .verde { color: var(--verde) !important; } .tarjeta .rojo, .rojo { color: var(--rojo) !important; }
.banda { border-left: 6px solid var(--ambar); background: #FBF3E3; padding: .9rem 1.1rem; border-radius: 4px 12px 12px 4px; margin: .6rem 0; }
.banda.ok { border-color: var(--verde); background: #E8F1EC; } .banda.mal { border-color: var(--rojo); background: #F8E6E1; }
[data-testid="stMarkdownContainer"] h2 { font-size: 1.4rem !important; margin-top: 1.1rem; }
[data-testid="stSidebar"] { background: var(--papel2); border-right: 1px solid var(--linea); }
.descargo { color: var(--gris); font-size: .78rem; border-top: 1px solid var(--linea); padding-top: .6rem; margin-top: 2rem; }
@media (max-width: 900px) { .tarjeta { margin-bottom: .8rem; } h1 { font-size: 1.8rem !important; } }
</style>
"""
DESCARGO = "Herramienta de análisis personal. No es asesoramiento financiero: las decisiones y el riesgo son tuyos."


def estilos() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(ttl=30, show_spinner=False)
def _corrida(stamp: str):
    return store.cargar(stamp)


def corrida_actual():
    stamps = store.listar()
    return _corrida(stamps[0]) if stamps else None


def bitacora():
    from src.operador.bitacora import Bitacora
    return Bitacora()


def ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def plata(x) -> str:
    return f"${x:,.0f}".replace(",", ".") if ok(x) else "—"


def plata_corta(x) -> str:
    if not ok(x):
        return "—"
    x = 0.0 if abs(x) < 0.5 else x  # sin "$-0"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.1f} M".replace(".", ",")
    if abs(x) >= 1e3:
        return f"${x / 1e3:,.0f} mil"
    return f"${x:,.0f}"


def pct(x, signo: bool = False) -> str:
    if not ok(x):
        return "—"
    x = 0.0 if abs(x) < 0.0005 else x
    return (f"{x:+.1%}" if signo else f"{x:.1%}").replace(".", ",")


def tarjeta(kicker: str, cifra: str, sub: str = "", clase_cifra: str = "") -> str:
    return (f'<div class="tarjeta"><div class="kicker">{kicker}</div>'
            f'<div class="cifra {clase_cifra}">{cifra}</div><div class="sub">{sub}</div></div>')


def banda(texto: str, tono: str = "") -> None:
    st.markdown(f'<div class="banda {tono}">{texto}</div>', unsafe_allow_html=True)


def descargo() -> None:
    st.markdown(f'<div class="descargo">{DESCARGO}</div>', unsafe_allow_html=True)


def sin_datos() -> None:
    st.info("Todavía no hay ningún análisis. Tocá **Revisar ahora** en la barra de la izquierda (tarda un minuto).")


def nombres_rf(c) -> dict:
    rf = c.renta_fija if c is not None else None
    if rf is None or rf.empty or "nombre" not in rf.columns:
        return {}
    return rf["nombre"].to_dict()


def precio_actual(c, t: str) -> float | None:
    if t in c.ranking.index and ok(c.ranking.at[t, "precio_ars"]):
        return float(c.ranking.at[t, "precio_ars"])
    if not c.renta_fija.empty and t in c.renta_fija.index and ok(c.renta_fija.at[t, "precio_ars"]):
        return float(c.renta_fija.at[t, "precio_ars"])
    return None


def tabla_cartera(c) -> pd.DataFrame:
    """Posiciones valuadas: qué es, cuánto vale hoy y cuánto ganás o perdés."""
    pos = c.meta.get("cartera", {}).get("posiciones") or {}
    rfn, filas = nombres_rf(c), []
    for t, p in pos.items():
        rf = (not c.renta_fija.empty) and t in c.renta_fija.index
        mult = 0.01 if rf or p.get("tipo") in ("bono", "letra", "on") else 1.0
        px = precio_actual(c, t) or p.get("precio")
        costo = p.get("ppc")
        valor = p["cantidad"] * (px or 0) * mult
        ganancia = (px / costo - 1) if ok(costo) and costo and ok(px) else None
        if rf:
            que = CLASE_RF.get(c.renta_fija.at[t, "clase"], "Renta fija")
        else:
            que = TIPO.get(c.ranking.at[t, "tipo"] if t in c.ranking.index else p.get("tipo"), "Activo")
        filas.append({"Activo": nombre(t, rfn), "Símbolo": t, "Qué es": que, "Cantidad": p["cantidad"],
                      "Valor hoy": valor, "Ganancia": ganancia})
    df = pd.DataFrame(filas)
    if df.empty:
        return df
    total = c.meta["cartera"].get("valor_total") or df["Valor hoy"].sum()
    df["Peso"] = df["Valor hoy"] / total if total else 0
    return df.sort_values("Valor hoy", ascending=False).reset_index(drop=True)


def estado_operador() -> dict:
    from app.credenciales import modo_real_habilitado

    s, b = load_settings(), bitacora()
    est = b.estado()
    ultimo = b.eventos(ultimos=1, tipo="corrida")
    real = s.get("operador", {}).get("modo", "paper") == "live" and modo_real_habilitado()
    modo_k = "live" if real else "paper"
    aportes = ((est.get("aportes") or {}).get(modo_k) or {}).get("total")
    from src.operador.seguimiento import resumen
    seguimiento = resumen((est.get("seguimiento") or {}).get(modo_k))
    return {"pausado": bool(est.get("pausado")), "real": real, "modo": "Real" if real else "Práctica", "aportes": aportes, "seguimiento": seguimiento,
            "ultima": ultimo[0]["ts"][:16].replace("T", " ") if ultimo else None,
            "pedido": est.get("ultimo_pedido_fondos")}


def barra_lateral() -> None:
    e = estado_operador()
    with st.sidebar:
        st.markdown('<div class="kicker">Operador automático</div>', unsafe_allow_html=True)
        st.markdown("### ⏸ En pausa" if e["pausado"] else f"### ● Activo · {e['modo']}")
        st.caption(f"Última revisión: {e['ultima'] or 'todavía no corrió'}. Revisa solo cada 15 minutos con el "
                   "mercado abierto y opera cuando el análisis lo justifica.")
        if st.button("Revisar ahora", use_container_width=True,
                     help="Analiza todo de nuevo con precios actuales. No compra ni vende: solo actualiza lo que ves."):
            _revisar()


def _revisar() -> None:
    from src.servicio import correr

    s = load_settings()
    cfg = s.get("operador", {})
    broker = "iol" if estado_operador()["real"] else "paper"
    with st.status("Analizando el mercado…", expanded=False) as estado:
        try:
            correr(cfg.get("horizonte", "mediano"), cfg.get("perfil", "moderado"), broker, s, load_universe())
        except Exception as ex:
            estado.update(label="No se pudo completar el análisis", state="error")
            st.error(f"{type(ex).__name__}: {ex}")
            return
        estado.update(label="Listo", state="complete")
    st.cache_data.clear()
    st.rerun()


def chip(texto: str) -> str:
    from app.etiquetas import SENAL
    color = {"COMPRAR": "#1F5C4A", "AGREGAR": "#1F5C4A", "REDUCIR / VENDER": "#A33B2B", "EVITAR": "#A33B2B"}.get(texto, "#6B675F")
    return (f'<span style="color:{color};border:1px solid {color};border-radius:999px;padding:.1rem .6rem;'
            f'font-size:.8rem;font-weight:600">{SENAL.get(texto, texto)}</span>')


sin_corrida = sin_datos


def serie_usd(ticker: str, universe: list | None = None) -> pd.DataFrame | None:
    from datetime import date, timedelta

    from src.data.prices import load_ccl, load_many, to_usd

    a = next((x for x in load_universe() if x["ticker"] == ticker), None)
    if a is None:
        return None
    desde = date.today() - timedelta(days=3 * 365)
    if a["tipo"] == "cedear":
        return load_many([a["subyacente"]], desde).get(a["subyacente"])
    ars = load_many([f"{ticker}.BA"], desde).get(f"{ticker}.BA")
    return to_usd(ars, load_ccl(desde)) if ars is not None else None
