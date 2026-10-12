"""Reporte semanal de Gorostiaga Bursátil: macro, ADRs, recomendaciones de bancos y noticias por empresa."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.comun import descargo

st.markdown('<div class="kicker">Gorostiaga Bursátil · Reporte Semanal de Mercados</div>', unsafe_allow_html=True)
st.title("Reporte semanal")

try:
    from src.data import gorostiaga as g
except ImportError:
    st.error("Falta el módulo de reportes.")
    st.stop()

if st.button("Buscar reportes nuevos"):
    with st.spinner("Buscando en gorostiagabursatil.com…"):
        nuevos = g.actualizar()
    st.success(f"Nuevos: {[r.get('numero') for r in nuevos]}" if nuevos else "No hay reportes nuevos todavía "
               "(salen los lunes a última hora o los martes).")

reportes = g.cargar_historial()
if not reportes:
    st.info("Todavía no se bajó ningún reporte.")
    st.stop()

hist = pd.DataFrame([{"numero": r.get("numero"), "fecha": r.get("fecha"), "riesgo_pais": r.get("riesgo_pais"),
                      "ccl": r.get("ccl"), "brecha": r.get("brecha_pct")} for r in reportes])
fig = go.Figure()
fig.add_scatter(x=hist["fecha"], y=hist["riesgo_pais"], name="Riesgo país (pb)", mode="lines+markers",
                line=dict(color="#A33B2B"))
fig.add_scatter(x=hist["fecha"], y=hist["ccl"], name="CCL ($)", mode="lines+markers", yaxis="y2",
                line=dict(color="#1F5C4A"))
fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                  plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.15),
                  yaxis=dict(gridcolor="#E2DACB"), yaxis2=dict(overlaying="y", side="right", showgrid=False),
                  font=dict(family="Inter", color="#1C1B19"))
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

num = st.selectbox("Reporte", [r["numero"] for r in reversed(reportes)],
                   format_func=lambda n: next(f"n°{n} · {r.get('fecha')}" for r in reportes if r["numero"] == n))
r = next(x for x in reportes if x["numero"] == num)
st.markdown(f"**Resumen.** {r.get('resumen') or 's/d'}")
if r.get("url"):
    st.caption(f"Fuente: {r['url']}")

t1, t2, t3 = st.tabs(["Recomendaciones de bancos", "ADRs argentinos", "Noticias por empresa"])
with t1:
    rec = pd.DataFrame(r.get("recomendaciones", []))
    st.dataframe(rec, use_container_width=True, hide_index=True) if not rec.empty else st.caption("Sin recomendaciones en este reporte.")
with t2:
    adrs = pd.DataFrame(r.get("adrs", []))
    if adrs.empty:
        st.caption("Este reporte no trae la tabla de ADRs como texto.")
    else:
        st.dataframe(adrs, use_container_width=True, hide_index=True)
with t3:
    for n in r.get("noticias", []):
        etiqueta = f"{n.get('ticker') or '—'} · {n.get('empresa', '')} · {', '.join(n.get('eventos', [])) or 'noticia'}"
        with st.expander(etiqueta):
            st.text(n.get("texto", ""))
if r.get("avisos"):
    st.caption("Avisos del lector: " + "; ".join(r["avisos"]))
st.caption("Los reportes se usan como contexto (eventos, precios objetivo, macro). No generan órdenes por sí solos.")
descargo()
