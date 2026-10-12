"""Nombres legibles para todo lo que la app muestra. Nada de nombres internos en pantalla."""
from __future__ import annotations

CLASE = {"acciones_ar": "Acciones argentinas", "cedears": "CEDEARs (empresas de afuera)",
         "bonos_usd": "Bonos en dólares", "pesos": "Inversiones en pesos", "oro": "Oro (refugio)", "caja": "Efectivo"}
CLASE_RF = {"soberano_usd": "Bono del Estado en dólares", "on_usd": "Obligación negociable (deuda de empresa)",
            "lecap": "Letra en pesos a tasa fija", "boncap": "Bono en pesos a tasa fija",
            "cer": "Bono en pesos ajustado por inflación", "dual": "Bono dual"}
TIPO = {"accion": "Acción argentina", "cedear": "CEDEAR", "bono": "Bono", "letra": "Letra", "on": "Obligación negociable"}
SECTOR = {
    "bancos": "Bancos", "financiero": "Servicios financieros", "utilities": "Energía eléctrica y gas",
    "energia": "Petróleo y gas", "materiales": "Industria y materiales", "holding": "Holding",
    "agro": "Agro", "real_estate": "Inmobiliario", "telecom": "Telecomunicaciones", "consumo": "Consumo",
    "infraestructura": "Infraestructura", "salud": "Salud", "etf_indices": "Índice (fondo de muchas empresas)",
    "etf_sector": "Fondo sectorial", "metales": "Oro y plata", "tecnologia": "Tecnología",
    "consumo_ext": "Consumo (exterior)", "financiero_ext": "Finanzas (exterior)", "energia_ext": "Petróleo (exterior)",
    "mineria": "Minería", "salud_ext": "Salud (exterior)", "industria_ext": "Industria (exterior)",
}
SENAL = {"COMPRAR": "Comprar", "AGREGAR": "Sumar más", "MANTENER": "Mantener", "NO COMPRAR": "Neutral",
         "ESPERAR (sobrecompra)": "Esperar: subió muy rápido", "ESPERAR (tendencia bajista)": "Esperar: viene bajando",
         "ILÍQUIDA (no comprar)": "Poco volumen: no comprar", "REDUCIR / VENDER": "Vender",
         "EVITAR": "Evitar", "SIN DATOS": "Sin datos"}
REGIMEN = {"favorable": "Favorable", "neutral": "Neutral", "adverso": "Adverso", "sin datos": "Sin datos"}
PERFIL = {
    "conservador": "Conservador: prioriza no perder. Más bonos y pesos, menos acciones.",
    "moderado": "Moderado: equilibrio entre crecer y cuidar. Mitad acciones, mitad renta fija.",
    "moderado_agresivo": "Medio agresivo: apunta a crecer fuerte, con algo de bonos para amortiguar las caídas.",
    "agresivo": "Agresivo: busca el máximo crecimiento y acepta caídas fuertes. Mayormente acciones.",
}

NOMBRE = {
    "ALUA": "Aluar", "BBAR": "BBVA Argentina", "BMA": "Banco Macro", "BYMA": "Bolsas y Mercados Argentinos",
    "CEPU": "Central Puerto", "COME": "Sociedad Comercial del Plata", "CRES": "Cresud", "EDN": "Edenor",
    "GGAL": "Grupo Galicia", "IRSA": "IRSA", "LOMA": "Loma Negra", "METR": "Metrogas", "PAMP": "Pampa Energía",
    "SUPV": "Grupo Supervielle", "TECO2": "Telecom Argentina", "TGNO4": "Transportadora Gas del Norte",
    "TGSU2": "Transportadora Gas del Sur", "TRAN": "Transener", "TXAR": "Ternium Argentina", "VALO": "Grupo Valores",
    "YPFD": "YPF", "ECOG": "Ecogas", "CVH": "Cablevisión Holding", "BHIP": "Banco Hipotecario",
    "BPAT": "Banco Patagonia", "MORI": "Morixe", "AUSO": "Autopistas del Sol", "OEST": "Grupo Concesionario del Oeste",
    "AGRO": "Agrometal", "SAMI": "San Miguel", "INVJ": "Inversora Juramento", "LEDE": "Ledesma", "CADO": "Carlos Casado",
    "HARG": "Holcim Argentina", "CELU": "Celulosa Argentina", "FERR": "Ferrum", "FIPL": "Fiplasto", "BOLT": "Boldt",
    "MOLA": "Molinos Agro", "MOLI": "Molinos Río de la Plata", "SEMI": "Molinos Juan Semino", "HAVA": "Havanna",
    "PATA": "La Anónima", "GARO": "Garovaglio y Zorraquín", "LONG": "Longvie", "GRIM": "Grimoldi", "RIGO": "Rigolleau",
    "INTR": "Compañía Introductora", "CECO2": "Central Costanera", "DGCU2": "Distribuidora Gas Cuyana",
    "CGPA2": "Camuzzi Gas Pampeana", "GBAN": "Naturgy BAN", "CAPX": "Capex", "CTIO": "Consultatio",
    "GCDI": "GCDI (TGLT)", "GCLA": "Grupo Clarín", "ROSE": "Instituto Rosenbusch", "DOME": "Domec", "CARC": "Carboclor",
    "SPY": "S&P 500 (las 500 mayores de EE.UU.)", "QQQ": "Nasdaq 100 (tecnológicas de EE.UU.)",
    "DIA": "Dow Jones (30 grandes de EE.UU.)", "IWM": "Russell 2000 (empresas chicas de EE.UU.)",
    "EEM": "Mercados emergentes", "EWZ": "Brasil", "XLE": "Petroleras de EE.UU.", "XLF": "Bancos de EE.UU.",
    "URA": "Uranio", "ARKK": "Innovación (ARK)", "GLD": "Oro", "SLV": "Plata", "AAPL": "Apple", "MSFT": "Microsoft",
    "NVDA": "Nvidia", "GOOGL": "Google", "META": "Meta (Facebook)", "AMD": "AMD", "AVGO": "Broadcom", "INTC": "Intel",
    "QCOM": "Qualcomm", "TSM": "TSMC", "ASML": "ASML", "ORCL": "Oracle", "ADBE": "Adobe", "CRM": "Salesforce",
    "GLOB": "Globant", "AMZN": "Amazon", "TSLA": "Tesla", "NFLX": "Netflix", "MELI": "Mercado Libre", "BABA": "Alibaba",
    "KO": "Coca-Cola", "PEP": "PepsiCo", "WMT": "Walmart", "COST": "Costco", "NU": "Nubank", "JPM": "JPMorgan",
    "V": "Visa", "MA": "Mastercard", "BRKB": "Berkshire Hathaway", "ITUB": "Itaú", "BBD": "Bradesco",
    "XOM": "ExxonMobil", "CVX": "Chevron", "VIST": "Vista Energy", "PBR": "Petrobras", "VALE": "Vale",
    "NEM": "Newmont (oro)", "B": "Barrick (oro)", "PAAS": "Pan American Silver", "LLY": "Eli Lilly",
    "JNJ": "Johnson & Johnson", "PFE": "Pfizer", "UNH": "UnitedHealth", "BA": "Boeing",
}


def nombre(ticker: str, rf_nombres: dict | None = None) -> str:
    if ticker in NOMBRE:
        return NOMBRE[ticker]
    if rf_nombres and ticker in rf_nombres and rf_nombres[ticker]:
        return str(rf_nombres[ticker])
    return ticker


def con_nombre(ticker: str, rf_nombres: dict | None = None) -> str:
    n = nombre(ticker, rf_nombres)
    return ticker if n == ticker else f"{n} ({ticker})"
