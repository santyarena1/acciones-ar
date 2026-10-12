"""Renta fija: bonos en dólares y letras/bonos en pesos, con su TIR, duration y valor relativo."""
import plotly.graph_objects as go
import streamlit as st

from app.comun import corrida_actual, descargo, sin_corrida

NOMBRES = {"soberano_usd": "Bonos del Estado en dólares", "on_usd": "Deuda de empresas en dólares (ONs)",
           "lecap": "Letras en pesos a tasa fija (Lecaps)", "boncap": "Bonos en pesos a tasa fija (Boncaps)",
           "cer": "Bonos en pesos que ajustan por inflación (CER)", "dual": "Duales"}
COLORES = {"soberano_usd": "#1F5C4A", "on_usd": "#4E8C77", "lecap": "#B7791F", "boncap": "#D29A3C",
           "cer": "#A33B2B", "dual": "#6B675F"}

c = corrida_actual()
st.markdown('<div class="kicker">Bonos y letras</div>', unsafe_allow_html=True)
st.title("Renta fija")
if c is None:
    sin_corrida()
    st.stop()

rf = c.renta_fija
if rf is None or rf.empty:
    st.info("Este análisis no tiene datos de renta fija. Actualizá el análisis para incluirlos.")
    st.stop()

st.caption("**Rinde por año**: lo que ganás por año si comprás hoy y lo mantenés hasta que vence. "
           "**Duración**: cuánto se mueve el precio si cambian las tasas (más duración = más riesgo y más potencial). "
           "**Barato/caro**: si rinde más o menos que otros parecidos.")

objetivos = c.objetivos if c.objetivos is not None else None
dur = next((x for x in ("duration", "duration_mod", "md") if x in rf.columns), None)
if dur and "tir" in rf.columns:
    fig = go.Figure()
    for clase, sub in rf.groupby("clase"):
        fig.add_scatter(x=sub[dur], y=sub["tir"], mode="markers+text", text=sub.index, textposition="top center",
                        name=NOMBRES.get(clase, clase), marker=dict(size=10, color=COLORES.get(clase, "#1C1B19")))
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(title="Duración (años)", gridcolor="#E2DACB"),
                      yaxis=dict(title="Rinde por año", tickformat=".0%", gridcolor="#E2DACB"),
                      legend=dict(orientation="h", y=1.1), font=dict(family="Inter", color="#1C1B19"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

for clase in [x for x in NOMBRES if x in set(rf["clase"])]:
    sub = rf[rf["clase"] == clase].copy()
    if objetivos is not None and not objetivos.empty:
        sub["en_objetivo"] = sub.index.map(lambda t: float(objetivos["peso_objetivo"].get(t, 0) or 0))
    orden = "score_rf" if "score_rf" in sub.columns else sub.columns[0]
    st.subheader(NOMBRES[clase])
    cfg = {"tir": st.column_config.NumberColumn("TIR", format="percent"),
           "tem": st.column_config.NumberColumn("TEM", format="percent"),
           "spread_vs_curva": st.column_config.NumberColumn("Spread vs. curva", format="percent"),
           "score_rf": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
           "en_objetivo": st.column_config.NumberColumn("Peso objetivo", format="percent")}
    vista = sub.sort_values(orden, ascending=False)
    columnas = {"nombre": "Nombre", "precio_ars": "Precio (cada 100)", "tir": "Rinde por año", "duration": "Duración (años)",
                "vencimiento": "Vence", "senal_rv": "Barato o caro", "score_rf": "Nota", "motivo_no_apto": "Por qué no compra",
                "en_objetivo": "En cartera objetivo"}
    vista = vista[[c for c in columnas if c in vista.columns]].rename(columns=columnas)
    st.dataframe(vista, use_container_width=True, column_config={
        "Rinde por año": st.column_config.NumberColumn(format="percent"),
        "Nota": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
        "En cartera objetivo": st.column_config.NumberColumn(format="percent"),
        "Duración (años)": st.column_config.NumberColumn(format="%.1f"),
        "Precio (cada 100)": st.column_config.NumberColumn(format="$ %.2f")})
descargo()
