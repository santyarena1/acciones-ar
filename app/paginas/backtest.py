"""Backtest: cómo le hubiera ido a la estrategia (solo score técnico) contra comprar todo parejo."""
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.comun import descargo, load_settings, load_universe, pct

st.markdown('<div class="kicker">Validación histórica</div>', unsafe_allow_html=True)
st.title("¿Cómo le hubiera ido?")
st.caption("Simula la estrategia del operador en el pasado, en dólares y con comisiones, y la compara contra "
           "comprar todo en partes iguales. **Ojo**: no usa datos de balances (no hay históricos confiables) y usa la "
           "lista de activos de hoy, así que el pasado se ve un poco mejor de lo que fue.")


@st.cache_data(ttl=3600, show_spinner=False)
def correr_bt(universo: str, desde: str, top_n: int, score_min: int, costo: int):
    from src.backtest.engine import run_backtest
    from src.pipeline import load_prices

    grupos = {"Argentina": ["lider", "general"], "CEDEARs": ["cedears"], "Todo": None}[universo]
    s = load_settings()
    s["datos"]["historia_anios"] = max(1, date.today().year - int(desde[:4]) + 1)
    p = load_prices(load_universe(grupos=grupos), s)
    usd = {t: df[df.index >= pd.Timestamp(desde)] for t, df in p.usd.items()}
    return run_backtest(usd, top_n, score_min, costo)


b = load_settings()["backtest"]
c1, c2, c3, c4, c5 = st.columns(5)
universo = c1.selectbox("Universo", ["Argentina", "CEDEARs", "Todo"])
desde = c2.selectbox("Desde", ["2018-01-01", "2020-01-01", "2022-01-01", "2023-01-01"])
top_n = c3.number_input("Cantidad de activos", 3, 20, int(b["top_n"]))
score_min = c4.number_input("Score mínimo", 30, 90, int(b["score_minimo"]))
costo = c5.number_input("Costo por lado (bps)", 0, 200, int(b["costo_bps"]))

if st.button("Correr backtest", type="primary"):
    with st.spinner("Bajando historia y simulando… (la primera vez tarda)"):
        try:
            st.session_state["bt"] = correr_bt(universo, desde, int(top_n), int(score_min), int(costo))
        except Exception as e:
            st.error(f"{type(e).__name__}: {e}")

res = st.session_state.get("bt")
if res:
    e, bm = res["estrategia"], res["benchmark"]
    k = st.columns(4)
    k[0].metric("Rendimiento anual (CAGR)", pct(e.get("cagr")), pct(e.get("cagr", 0) - bm.get("cagr", 0), True) + " vs. benchmark")
    k[1].metric("Peor caída", pct(e.get("max_drawdown")), f"benchmark {pct(bm.get('max_drawdown'))}", delta_color="off")
    k[2].metric("Rendimiento por riesgo (Sharpe)", e.get("sharpe_rf0"), f"benchmark {bm.get('sharpe_rf0')}", delta_color="off")
    k[3].metric("Meses mejor que el benchmark", pct(e.get("meses_mejor_que_benchmark")))
    cv = res["curvas"]
    fig = go.Figure()
    fig.add_scatter(x=cv.index, y=cv["estrategia"], name="Estrategia", line=dict(color="#1F5C4A", width=2))
    fig.add_scatter(x=cv.index, y=cv["benchmark"], name="Comprar todo parejo", line=dict(color="#9C9384", width=1.5))
    fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", yaxis=dict(type="log", gridcolor="#E2DACB", title="USD 1 →"),
                      legend=dict(orientation="h", y=1.08), font=dict(family="Inter", color="#1C1B19"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.subheader("Año por año")
    st.dataframe(res["anuales"].style.format("{:.1%}"), use_container_width=True)
    st.dataframe(pd.DataFrame({"Estrategia": e, "Benchmark": bm}), use_container_width=True)
    st.caption(f"Período {res['desde']} → {res['hasta']}. Rendimientos pasados no garantizan resultados futuros.")
descargo()
