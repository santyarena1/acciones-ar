"""CLI del analizador de inversiones (acciones, CEDEARs, bonos y letras) para IOL.

  python main.py app                                   # abre la app web en el navegador
  python main.py analizar  --horizonte mediano --perfil moderado [--broker paper|iol]
  python main.py ejecutar  reports/corridas/XXXX/ordenes.csv [--live]
  python main.py backtest  --desde 2018-01-01 [--universo ar|cedears|todo]
  python main.py backtest-tactico [--desde 2008-01-01] [--perfil moderado_agresivo] [--freq ME|W-FRI]
  python main.py reportes                              # baja y parsea los reportes semanales de Gorostiaga
  python main.py login-test
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.config import REPORTS_DIR, ROOT, load_settings, load_universe

load_dotenv()
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 24)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DESCARGO = "Herramienta de análisis personal, no es asesoramiento financiero."
COLS_RANKING = ["tipo", "sector", "score", "senal", "score_tecnico", "score_fundamental", "precio_ars",
                "mom_6m", "vol_anual", "liquido", "alertas"]


def cmd_analizar(args, settings, universe):
    from src.servicio import correr

    c = correr(args.horizonte, args.perfil, args.broker, settings, universe)
    print("\n" + c.guia)
    print(f"\nTop 20 del ranking ({args.horizonte}, en USD):\n")
    print(c.ranking[COLS_RANKING].head(20).to_string())
    if not c.ordenes.empty:
        print(f"\nÓrdenes sugeridas en {c.dir / 'ordenes.csv'}")
        print(f"Revisalas y después: python main.py ejecutar \"{c.dir / 'ordenes.csv'}\"")
    print(f"\nCorrida guardada en {c.dir}\n{DESCARGO}")


def cmd_ejecutar(args, settings, universe):
    from src.portfolio.risk import RiskError, validate_orders
    from src.servicio import crear_broker

    try:
        ordenes = pd.read_csv(args.archivo)
    except (FileNotFoundError, pd.errors.EmptyDataError) as e:
        sys.exit(f"No pude leer las órdenes de {args.archivo}: {e}")
    if args.live and os.getenv("IOL_LIVE_TRADING") != "1":
        sys.exit("Modo real deshabilitado: poné IOL_LIVE_TRADING=1 en .env si de verdad querés operar.")
    broker = crear_broker("iol" if args.live else "paper", settings)
    posiciones, caja = broker.get_positions(), broker.get_cash_ars()
    valor_total = caja + sum(float(p.get("valorizado") or 0) for p in posiciones.values())
    try:
        # ventas <= tenencia, compras <= caja, ninguna orden > orden_maxima_pct_cartera de la cartera
        ordenes = validate_orders(ordenes, settings, posiciones, caja, valor_total=valor_total)
    except RiskError as e:
        sys.exit(f"Bloqueado por límites de riesgo: {e}")
    if ordenes.empty:
        sys.exit("El archivo no tiene órdenes.")

    print(f"\nModo: {'REAL (IOL)' if args.live else 'PAPER (simulado)'}\n")
    print(ordenes[["ticker", "lado", "cantidad", "precio_limite", "monto_ars"]].to_string(index=False))
    if args.live and input("\nEscribí CONFIRMAR para enviar estas órdenes a IOL: ").strip() != "CONFIRMAR":
        sys.exit("Cancelado. No se envió nada.")
    for _, o in ordenes.iterrows():
        mult = float(o["mult"]) if "mult" in o and pd.notna(o["mult"]) else 1.0
        try:
            extra = {"tipo": "bono"} if broker.nombre == "paper" and mult != 1.0 else {}
            r = broker.place_order(o["ticker"], o["lado"], int(o["cantidad"]), float(o["precio_limite"]),
                                   mult=mult, **extra)
        except Exception as e:
            r = {"estado": "error", "mensaje": str(e)}
        print(f"  {o['lado']:8} {int(o['cantidad']):>8} {o['ticker']:6} @ {o['precio_limite']:>12,.2f} -> {r}")


def cmd_backtest(args, settings, universe):
    from src.backtest.engine import run_backtest
    from src.pipeline import load_prices

    grupos = {"ar": ["lider", "general"], "cedears": ["cedears"], "todo": None}[args.universo]
    uni = load_universe(grupos=grupos)
    settings = {**settings, "datos": {**settings["datos"], "historia_anios": max(1, date.today().year - int(args.desde[:4]) + 1)}}
    print(f"Bajando historia de {len(uni)} activos (yfinance) y CCL...")
    precios = load_prices(uni, settings)
    usd = {t: df[df.index >= pd.Timestamp(args.desde)] for t, df in precios.usd.items()}
    b, e = settings["backtest"], settings.get("estrategia") or {}
    if args.universo == "ar" and e.get("acciones_ar") == "equiponderado":
        from src.backtest.engine import run_backtest_equiponderado
        lider = {a["ticker"] for a in uni if a["panel"] == "lider"}
        res = run_backtest_equiponderado(usd, precios.monto_ars, lider, e.get("n_acciones_ar", 8),
                                         e.get("margen_salida_liquidez", 3), b["costo_bps"],
                                         stop=-0.25 if e.get("salir_por_stop") else -9.0)
        titulo = "equiponderado de las más líquidas del panel líder (liquidez point-in-time)"
    else:
        res = run_backtest(usd, b["top_n"], b["score_minimo"], b["costo_bps"], b.get("score_salida", 37),
                           b.get("filtro_tendencia", True))
        titulo = "solo score técnico"
    print(f"\nBacktest {res['desde']} -> {res['hasta']} (USD, {titulo}, universo actual)\n")
    print(pd.DataFrame({"estrategia": res["estrategia"], "benchmark": res["benchmark"]}).to_string())
    print("\nRendimiento por año:\n" + res["anuales"].to_string())
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"backtest_{args.universo}_{datetime.now():%Y%m%d_%H%M}.csv"
    res["curvas"].to_csv(out)
    print(f"\nCurvas guardadas en {out}. Rendimientos pasados no garantizan futuros.")


def cmd_backtest_tactico(args, settings, universe):
    """Perfil fijo vs. régimen AR vs. riesgo global vs. rotación (2008-2026, USD, con proxies)."""
    from src.backtest import tactico_correr as tc

    print("Bajando historia (ETFs, ADRs argentinos, VIX, tasas, riesgo país)...")
    c = tc.comparar(tc.cargar(settings), settings, args.perfil, args.freq, args.desde)
    print(f"\nBacktest táctico {args.desde} -> hoy, perfil {args.perfil}, rebalanceo {args.freq}, USD")
    tc.imprimir(c)
    print("\nProxies: acciones AR = ADRs; CEDEARs = ETFs de sectores/regiones; bonos USD = sintético (riesgo país +"
          " UST10); pesos = letras del Tesoro de EE.UU. (no hay historia de Lecaps); caja = 0%.")
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"backtest_tactico_{datetime.now():%Y%m%d_%H%M}.csv"
    pd.DataFrame({n: r["curva"] for n, r in c["resultados"].items()}).to_csv(out)
    print(f"Curvas en {out}. {DESCARGO}")


def cmd_operar(args, settings, universe):
    """Un ciclo del operador automático. Real solo si operador.modo=live (o --modo live) e IOL_LIVE_TRADING=1."""
    from src.operador.ejecutor import operar

    r = operar(settings, universe, modo=args.modo, forzar_horario=args.forzar_horario)
    print(f"[{r.estado}] {r.mensaje}")
    if r.pedido_fondos:
        print(f"Pedido de fondos: {r.pedido_fondos['texto']}")
    if r.corrida:
        print(f"Análisis: reports/corridas/{r.corrida}")
    sys.exit(1 if r.estado == "error" else 0)


def cmd_reportes(args, settings, universe):
    from src.data import gorostiaga as g

    nuevos = g.actualizar()
    print(f"Reportes nuevos: {[r.get('numero') for r in nuevos] or 'ninguno'}")
    for r in g.cargar_historial()[-3:]:
        print(f"  n°{r.get('numero')} {r.get('fecha')}: riesgo país {r.get('riesgo_pais')}, CCL {r.get('ccl')}, "
              f"{len(r.get('noticias', []))} noticias, {len(r.get('recomendaciones', []))} recomendaciones")


def cmd_login_test(args, settings, universe):
    from src.servicio import crear_broker

    b = crear_broker("iol", settings)
    pos = b.get_positions()
    print(f"Login OK. Activos en cartera: {len(pos)} | Caja ARS disponible: ${b.get_cash_ars():,.0f}")


def cmd_app(args, settings, universe):
    app = Path(ROOT) / "app" / "app.py"
    # se lanza desde la carpeta del proyecto para que tome .streamlit/config.toml (tema y opciones)
    sys.exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), "--server.headless", "false"],
                             cwd=str(ROOT)))


def main(argv=None):
    settings, universe = load_settings(), load_universe()
    ap = argparse.ArgumentParser(description="Analizador de inversiones para IOL")
    sub = ap.add_subparsers(dest="cmd", required=True)
    horizontes, perfiles = list(settings["pesos_horizonte"]), list(settings["perfiles"])

    p = sub.add_parser("analizar")
    p.add_argument("--horizonte", choices=horizontes, default=settings["horizonte_default"])
    p.add_argument("--perfil", choices=perfiles, default=settings["perfil_default"])
    p.add_argument("--broker", choices=["paper", "iol"], default="paper")
    p = sub.add_parser("ejecutar"); p.add_argument("archivo"); p.add_argument("--live", action="store_true")
    p = sub.add_parser("backtest"); p.add_argument("--desde", default="2018-01-01")
    p.add_argument("--universo", choices=["ar", "cedears", "todo"], default="ar")
    p = sub.add_parser("backtest-tactico", help="valida la capa táctica (riesgo global, rotación)")
    p.add_argument("--desde", default="2008-01-01")
    p.add_argument("--perfil", choices=perfiles, default="moderado_agresivo")
    p.add_argument("--freq", choices=["ME", "W-FRI"], default="ME")
    p = sub.add_parser("operar", help="un ciclo del operador automático")
    p.add_argument("--modo", choices=["paper", "live"], default=None, help="por defecto: operador.modo en settings")
    p.add_argument("--forzar-horario", action="store_true", help="correr aunque el mercado esté cerrado (pruebas)")
    sub.add_parser("reportes"); sub.add_parser("login-test"); sub.add_parser("app")

    args = ap.parse_args(argv)
    {"analizar": cmd_analizar, "ejecutar": cmd_ejecutar, "backtest": cmd_backtest, "reportes": cmd_reportes,
     "backtest-tactico": cmd_backtest_tactico,
     "operar": cmd_operar, "login-test": cmd_login_test, "app": cmd_app}[args.cmd](args, settings, universe)


if __name__ == "__main__":
    main()
