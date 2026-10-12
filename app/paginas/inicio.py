"""Inicio: tu plata hoy, qué hizo el operador y qué está pensando."""
import plotly.graph_objects as go
import streamlit as st

from app.comun import (banda, bitacora, corrida_actual, descargo, estado_operador, nombres_rf, pct, plata_corta, sin_datos, tabla_cartera, tarjeta)
from app.etiquetas import CLASE, REGIMEN, nombre

c = corrida_actual()
e = estado_operador()
st.markdown('<div class="kicker">Inicio</div>', unsafe_allow_html=True)
st.title("Tu plata, hoy")
if c is None:
    sin_datos()
    st.stop()

if not e["real"]:
    banda("Estás en <b>modo práctica</b>: el operador opera con plata simulada para que veas cómo trabaja. "
          "Cuando quieras usar tu cuenta de IOL, andá a <b>Configuración</b>.")
if e["pausado"]:
    banda("El operador está <b>en pausa</b>: no compra ni vende hasta que lo reactives en Configuración.", "mal")
if e["pedido"]:
    banda(f"💰 <b>El operador pide fondos.</b> {e['pedido'].get('texto', '')}", "ok")

cart = c.meta.get("cartera", {})
tabla = tabla_cartera(c)
invertido = tabla["Valor hoy"].sum() if not tabla.empty else 0
ganancias = tabla.dropna(subset=["Ganancia"]) if not tabla.empty else tabla
gan_pesos = (ganancias["Valor hoy"] - ganancias["Valor hoy"] / (1 + ganancias["Ganancia"])).sum() if not ganancias.empty else 0
macro = c.meta.get("macro", {})

from src.operador.aportes import rendimiento  # noqa: E402

valor = cart.get("valor_total")
gan, gan_pct = rendimiento(valor or 0, e.get("aportes") or 0)
k = st.columns(4)
k[0].markdown(tarjeta("Valor total", plata_corta(valor), f"efectivo {plata_corta(cart.get('caja'))}"),
              unsafe_allow_html=True)
k[1].markdown(tarjeta("Lo que pusiste", plata_corta(e.get("aportes")), "suma de tus depósitos"), unsafe_allow_html=True)
k[2].markdown(tarjeta("Ganancia real", plata_corta(gan) if e.get("aportes") else "—",
                      (pct(gan_pct, True) + " sobre lo que pusiste") if gan_pct is not None else "se calcula en la primera revisión",
                      "verde" if gan >= 0 else "rojo"), unsafe_allow_html=True)
seg = e.get("seguimiento") or {}
dif = seg.get("diferencia")
k[3].markdown(tarjeta("vs. no hacer nada", pct(dif, True) if seg else "—",
                      (f"operador {pct(seg['operador'], True)} · S&P+Merval {pct(seg['no_hacer_nada'], True)}") if seg
                      else "se mide desde la primera revisión", "verde" if (dif or 0) >= 0 else "rojo"),
              unsafe_allow_html=True)
st.write("")
izq, der = st.columns([1, 1.25], gap="large")
with izq:
    st.subheader("Cómo está repartida")
    asig, actual = c.meta.get("asignacion", {}), c.meta.get("actual_por_clase", {})
    clases = list(asig)
    fig = go.Figure()
    fig.add_bar(y=[CLASE.get(x, x) for x in clases], x=[actual.get(x, 0) for x in clases], orientation="h",
                name="Hoy", marker_color="#C9BFAE")
    fig.add_bar(y=[CLASE.get(x, x) for x in clases], x=[asig[x] for x in clases], orientation="h",
                name="Lo que busca el operador", marker_color="#1F5C4A")
    fig.update_layout(barmode="group", height=300, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", xaxis=dict(tickformat=".0%", gridcolor="#E2DACB"),
                      legend=dict(orientation="h", y=-0.2), font=dict(family="Inter", color="#1C1B19"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.caption(f"Perfil **{c.meta.get('perfil')}**. El reparto sigue tu perfil: los ajustes por momento (refugio, "
               "sectores, elecciones) se calculan y se muestran, pero están apagados porque en las pruebas 2008–2026 "
               "no mejoraron el resultado.")

with der:
    st.subheader("Qué hizo el operador")
    ords = [ev for ev in bitacora().eventos(ultimos=200, tipo="orden")][-8:]
    if not ords:
        st.caption("Todavía no hizo operaciones.")
    for ev in reversed(ords):
        verbo = "Compró" if ev["lado"] == "COMPRAR" else "Vendió"
        ok_ = ev.get("estado") not in ("rechazada", "error")
        estado = "" if ok_ else f" — <span class='rojo'>no se pudo ({ev.get('mensaje') or ev.get('estado')})</span>"
        st.markdown(f"**{ev['ts'][8:10]}/{ev['ts'][5:7]} {ev['ts'][11:16]}** · {verbo} {ev['cantidad']:,} de "
                    f"**{nombre(ev['ticker'], nombres_rf(c))}**{estado}".replace(",", "."), unsafe_allow_html=True)
    st.subheader("Qué está pensando")
    motivos = macro.get("motivos") or []
    if motivos:
        st.markdown(f"**Argentina ({REGIMEN.get(macro.get('regimen'), '—').lower()}):** " + "; ".join(motivos) + ".")
    tac = c.meta.get("tactico") or {}
    if tac.get("motivos"):
        with st.expander("Cómo ve el mundo (riesgo global, sectores y eventos que se vienen)", expanded=True):
            for m in tac["motivos"]:
                st.markdown(f"- {m}")
    rep = c.meta.get("reporte_semanal") or {}
    if rep.get("resumen"):
        with st.expander(f"Lo que dijo el reporte semanal de Gorostiaga (n°{rep.get('numero')})"):
            st.write(rep["resumen"])
    pend = c.ordenes
    if pend is not None and not pend.empty:
        st.markdown(f"Con los precios de la última revisión, el plan ideal tiene **{len(pend)} movimientos**. "
                    "El operador los hace solo si con el mercado abierto los precios siguen dando.")
descargo()
