"""App web del operador. Se abre con doble click en Abrir_app.bat (o: python main.py app)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
st.set_page_config(page_title="Mi operador de inversiones", page_icon="📈", layout="wide")

from app.comun import barra_lateral, estilos  # noqa: E402

estilos()
P = ROOT / "app" / "paginas"
nav = st.navigation({
    "": [st.Page(P / "inicio.py", title="Inicio", icon=":material/home:", default=True),
         st.Page(P / "cartera.py", title="Mi cartera", icon=":material/account_balance_wallet:"),
         st.Page(P / "oportunidades.py", title="Oportunidades", icon=":material/trending_up:"),
         st.Page(P / "historial.py", title="Historial", icon=":material/receipt_long:"),
         st.Page(P / "configuracion.py", title="Configuración", icon=":material/settings:")],
    "Análisis avanzado": [
        st.Page(P / "activo.py", title="Ficha de un activo", icon=":material/query_stats:"),
        st.Page(P / "renta_fija.py", title="Bonos y letras", icon=":material/account_balance:"),
        st.Page(P / "reporte.py", title="Reporte semanal", icon=":material/newspaper:"),
        st.Page(P / "backtest.py", title="Cómo le hubiera ido", icon=":material/history:")],
})
barra_lateral()
nav.run()
