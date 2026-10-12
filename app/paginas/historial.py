"""Historial: todo lo que hizo el operador, en orden, y cómo evolucionó el valor de la cartera."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.comun import bitacora, corrida_actual, descargo, nombres_rf, plata
from app.etiquetas import nombre

st.markdown('<div class="kicker">Historial</div>', unsafe_allow_html=True)
st.title("Lo que hizo el operador")

b = bitacora()
_c = corrida_actual()
_rfn = nombres_rf(_c) if _c is not None else {}
corridas = pd.DataFrame(b.eventos(tipo="corrida"))
if not corridas.empty and "valor_total" in corridas and corridas["ts"].str[:10].nunique() >= 2:
    corridas["fecha"] = pd.to_datetime(corridas["ts"].str[:19])
    serie = corridas.groupby(corridas["fecha"].dt.date)["valor_total"].last()
    fig = go.Figure(go.Scatter(x=list(serie.index), y=serie.values, mode="lines+markers",
                               line=dict(color="#1F5C4A", width=2)))
    fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(gridcolor="#E2DACB", tickprefix="$"),
                      font=dict(family="Inter", color="#1C1B19"))
    st.subheader("Valor de la cartera")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

TEXTO = {
    "orden": lambda e: (f"{'Compró' if e['lado'] == 'COMPRAR' else 'Vendió'} {e['cantidad']:,} de "
                        f"**{nombre(e['ticker'], _rfn)}** a {plata(e.get('precio'))}"
                        + ("" if e.get("estado") not in ("rechazada", "error") else
                           f" — no se pudo: {e.get('mensaje') or e.get('estado')}")).replace(",", "."),
    "aporte": lambda e: ("🏦 Capital inicial: " if e.get("inicial") else ("🏦 Detectó un depósito de " if e.get("monto", 0) > 0
                         else "🏦 Detectó un retiro de ")) + plata(abs(e.get("monto", 0))),
    "pedido_fondos": lambda e: f"💰 Pidió fondos: {e.get('texto', '')}",
    "descartada": lambda e: f"No operó {nombre(e['ticker'], _rfn)}: el precio en vivo se alejó del analizado (protección).",
    "error": lambda e: f"⚠️ Error: {e.get('error', '')}",
    "pausa": lambda e: "⏸ Se pausó el operador.",
    "reanudar": lambda e: "▶ Se reactivó el operador.",
    "cancelacion": lambda e: f"Canceló una orden que había quedado pendiente ({e.get('simbolo')}).",
}
eventos = [e for e in b.eventos() if e.get("tipo") in TEXTO]
st.subheader("Movimientos")
if not eventos:
    st.caption("Todavía no hay movimientos.")
dia = None
for e in reversed(eventos[-300:]):
    if e["ts"][:10] != dia:
        dia = e["ts"][:10]
        st.markdown(f"#### {dia[8:10]}/{dia[5:7]}/{dia[:4]}")
    st.markdown(f"`{e['ts'][11:16]}` {TEXTO[e['tipo']](e)}")
descargo()
