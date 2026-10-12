"""Mi cartera: qué tenés, cuánto vale, cuánto ganás o perdés y por qué está ahí."""
import plotly.graph_objects as go
import streamlit as st

from app.comun import corrida_actual, descargo, ok, pct, plata, sin_datos, tabla_cartera
from app.etiquetas import SENAL
from src.guia import razones

c = corrida_actual()
st.markdown('<div class="kicker">Mi cartera</div>', unsafe_allow_html=True)
st.title("Lo que tenés")
if c is None:
    sin_datos()
    st.stop()

t = tabla_cartera(c)
cart = c.meta.get("cartera", {})
if t.empty:
    st.info(f"No hay inversiones todavía. Efectivo disponible: {plata(cart.get('caja'))}.")
    st.stop()

izq, der = st.columns([2.6, 1], gap="medium")
with izq:
    st.dataframe(t.drop(columns=["Símbolo", "Cantidad"]), use_container_width=True, hide_index=True,
                 height=min(640, 38 + 35 * len(t)),
                 column_config={
                     "Valor hoy": st.column_config.NumberColumn(format="$ %d"),
                     "Ganancia": st.column_config.NumberColumn(format="percent", help="Precio de hoy contra lo que se pagó"),
                     "Peso": st.column_config.ProgressColumn("Peso en la cartera", min_value=0, max_value=0.15,
                                                             format="percent"),
                     "Cantidad": st.column_config.NumberColumn(format="%d"),
                 })
    st.caption(f"Efectivo: {plata(cart.get('caja'))}. Los bonos se cuentan en nominales y su precio es cada 100.")
with der:
    por = t.groupby("Qué es")["Valor hoy"].sum().sort_values()
    fig = go.Figure(go.Pie(labels=por.index, values=por.values, hole=.55, sort=False, textinfo="percent",
                           marker=dict(colors=["#1F5C4A", "#4E8C77", "#B7791F", "#D29A3C", "#A33B2B", "#9C9384",
                                               "#C9BFAE"])))
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=-0.05), font=dict(family="Inter", color="#1C1B19"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

st.subheader("Por qué tiene cada cosa")
for _, f in t.iterrows():
    s = f["Símbolo"]
    if s in c.ranking.index:
        r = c.ranking.loc[s]
        motivo = "; ".join(razones(r)) or "sigue dentro de lo que busca el operador"
        aviso = f" ⚠️ {r['alertas']}" if r.get("alertas") else ""
        st.markdown(f"**{f['Activo']}** · {SENAL.get(r['senal'], r['senal'])} — {motivo}.{aviso}")
    elif not c.renta_fija.empty and s in c.renta_fija.index:
        r = c.renta_fija.loc[s]
        tir = f"rinde {pct(r['tir'])} anual" if ok(r.get("tir")) else "renta fija"
        st.markdown(f"**{f['Activo']}** · {tir} si se mantiene hasta el vencimiento "
                    f"({str(r.get('vencimiento', ''))[:10]}).")
descargo()
