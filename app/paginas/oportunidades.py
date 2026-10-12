"""Oportunidades: lo que el análisis ve mejor, explicado. La tabla completa queda abajo para quien quiera."""
import pandas as pd
import streamlit as st

from app.comun import corrida_actual, descargo, plata, sin_datos
from app.etiquetas import SECTOR, SENAL, TIPO, nombre
from src.guia import razones

c = corrida_actual()
st.markdown('<div class="kicker">Oportunidades</div>', unsafe_allow_html=True)
st.title("Lo que el análisis ve mejor")
if c is None:
    sin_datos()
    st.stop()

r = c.ranking.copy()
for col in ("score", "precio_ars", "mom_6m", "upside_consenso", "vol_anual"):
    if col in r.columns:
        r[col] = pd.to_numeric(r[col], errors="coerce")
st.caption("Cada activo tiene una **nota de 0 a 100** que junta cómo viene el precio (en dólares, comparado con "
           "el resto) y qué tan sana está la empresa. Más de 70 es zona de compra; menos de 40, de venta.")

tipo = st.segmented_control("Mostrar", ["Todo", "Acciones argentinas", "CEDEARs"], default="Todo")
if tipo == "Acciones argentinas":
    r = r[r["tipo"] == "accion"]
elif tipo == "CEDEARs":
    r = r[r["tipo"] == "cedear"]

compras = r[r["senal"].isin(["COMPRAR", "AGREGAR"])].head(9)
cols = st.columns(3)
for i, (t, f) in enumerate(compras.iterrows()):
    with cols[i % 3]:
        why = razones(f)
        st.markdown(
            f'<div class="tarjeta"><div class="kicker">{TIPO.get(f["tipo"], "")} · {SECTOR.get(f["sector"], f["sector"])}</div>'
            f'<div class="cifra" style="white-space:normal;font-size:1.25rem">{nombre(t)}</div>'
            f'<div class="sub">Nota <b>{f["score"]:.0f}</b> · {SENAL.get(f["senal"])} · {plata(f["precio_ars"])}</div>'
            f'<div class="sub" style="margin-top:.4rem">{"; ".join(why[:3]) or "nota alta"}</div></div>',
            unsafe_allow_html=True)
        st.write("")
if compras.empty:
    st.info("Hoy no hay nada en zona de compra en este grupo.")

with st.expander("Ver todos los activos analizados"):
    tabla = pd.DataFrame({
        "Activo": [nombre(t) for t in r.index], "Qué es": r["tipo"].map(TIPO), "Sector": r["sector"].map(SECTOR),
        "Nota": r["score"], "Qué hacer": r["senal"].map(SENAL), "Precio": r["precio_ars"],
        "Últimos 6 meses (USD)": r["mom_6m"], "Analistas": r["upside_consenso"], "Avisos": r["alertas"],
    })
    st.dataframe(tabla, use_container_width=True, hide_index=True, height=560, column_config={
        "Nota": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
        "Precio": st.column_config.NumberColumn(format="$ %.2f"),
        "Últimos 6 meses (USD)": st.column_config.NumberColumn(format="percent"),
        "Analistas": st.column_config.NumberColumn(format="percent", help="Cuánto suben según el precio objetivo de bancos (reporte semanal)"),
    })
    st.caption("Las que tienen poco volumen se analizan pero no se compran (cuesta salir).")
descargo()
