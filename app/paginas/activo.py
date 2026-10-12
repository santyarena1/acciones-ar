"""Detalle de un activo: precio en USD, por qué tiene ese score y qué dice el reporte semanal."""
import plotly.graph_objects as go
import streamlit as st

from app.comun import (chip, corrida_actual, descargo, load_universe, ok, pct, plata, plata_corta, serie_usd,
                        sin_corrida, tarjeta)
from app.etiquetas import SECTOR, TIPO, nombre
from src.guia import razones

c = corrida_actual()
st.markdown('<div class="kicker">Ficha</div>', unsafe_allow_html=True)
if c is None:
    st.title("Activo")
    sin_corrida()
    st.stop()

r = c.ranking
universe = load_universe()
t = st.selectbox("Elegí un activo", list(r.index),
                 format_func=lambda x: f"{nombre(x)} ({x}) · nota {r.at[x, 'score']:.0f}" if ok(r.at[x, "score"]) else nombre(x))
f = r.loc[t]
st.title(nombre(t))
st.markdown(chip(f["senal"]) + f'&nbsp; <span class="sub">{TIPO.get(f["tipo"], "")} · {SECTOR.get(f["sector"], f["sector"])}</span>',
            unsafe_allow_html=True)

k = st.columns(5)
k[0].markdown(tarjeta("Nota", f"{f['score']:.0f}" if ok(f["score"]) else "—", f.get("nota") or "técnico + fundamental"),
              unsafe_allow_html=True)
k[1].markdown(tarjeta("Precio BYMA", plata_corta(f["precio_ars"]) if ok(f["precio_ars"]) and f["precio_ars"] >= 1e5 else plata(f["precio_ars"]), f"USD {f['precio_usd']:.2f}" if ok(f["precio_usd"]) else ""),
              unsafe_allow_html=True)
k[2].markdown(tarjeta("6 meses (USD)", pct(f["mom_6m"], True), f"12 m: {pct(f['mom_12m_1m'], True)}"), unsafe_allow_html=True)
k[3].markdown(tarjeta("Volatilidad", pct(f["vol_anual"]), f"desde máximo: {pct(f['dist_max_52s'], True)}"),
              unsafe_allow_html=True)
k[4].markdown(tarjeta("Analistas", pct(f.get("upside_consenso"), True), "upside vs. precio objetivo"),
              unsafe_allow_html=True)

izq, der = st.columns([1.7, 1], gap="large")
with izq:
    df = serie_usd(t)
    if df is not None and not df.empty:
        s = df["close"]
        fig = go.Figure()
        fig.add_scatter(x=s.index, y=s, name="Precio USD", line=dict(color="#1C1B19", width=1.6))
        fig.add_scatter(x=s.index, y=s.rolling(50).mean(), name="Media 50", line=dict(color="#B7791F", width=1.2))
        fig.add_scatter(x=s.index, y=s.rolling(200).mean(), name="Media 200", line=dict(color="#1F5C4A", width=1.2, dash="dot"))
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", legend=dict(orientation="h", y=1.08),
                          yaxis=dict(gridcolor="#E2DACB", title="USD"), font=dict(family="Inter", color="#1C1B19"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("Acciones locales: precio en pesos dividido por el CCL de cada día. CEDEARs: precio del activo en EE.UU.")
    else:
        st.info("Sin serie de precios para graficar.")
with der:
    st.subheader("Por qué tiene esta nota")
    partes = {"Cómo viene el precio": f.get("tec_abs"), "Precio comparado con el resto": f.get("tec_rel"),
              "Salud de la empresa": f.get("fund_abs"), "Empresa comparada con sus pares": f.get("fund_rel")}
    for nombre, v in partes.items():
        st.progress(int(v) if ok(v) else 0, text=f"{nombre}: {v:.0f}" if ok(v) else f"{nombre}: sin datos")
    for frase in razones(f) or ["Sin señales destacadas."]:
        st.markdown(f"- {frase}")
    if f.get("alertas"):
        st.warning(f["alertas"])

ctx = c.meta.get("contexto", {}).get(t, {})
if ctx:
    st.subheader("Qué dice el reporte semanal")
    for rec in ctx.get("recomendaciones", []):
        objetivo = f" · objetivo USD {rec['precio_objetivo_usd']:,.2f}" if rec.get("precio_objetivo_usd") else ""
        st.markdown(f"- **{rec.get('fuente')}**: {rec.get('rating') or 's/d'}{objetivo} "
                    f"(reporte n°{rec.get('numero')}, {rec.get('fecha')})")
    for n in ctx.get("noticias", [])[:4]:
        with st.expander(f"n°{n.get('numero')} · {n.get('fecha')} · {', '.join(n.get('eventos', [])) or 'noticia'}"):
            st.text(n.get("texto", ""))
descargo()
