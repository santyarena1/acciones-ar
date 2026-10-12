"""CLI del analizador de acciones argentinas.

  python main.py analizar  --horizonte mediano
  python main.py ordenes   --horizonte mediano --broker paper|iol
  python main.py ejecutar  reports/ordenes_XXXX.csv [--live]
  python main.py backtest  --desde 2018-01-01
  python main.py login-test
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime

import pandas as pd
from dotenv import load_dotenv

from src.config import REPORTS_DIR, load_settings, load_universe, sector_map

load_dotenv()
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

DESCARGO = "Herramienta de análisis personal, no es asesoramiento financiero."


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def _iol_client():
    from src.broker.iol import IOLClient
    return IOLClient()


def _broker(nombre: str, settings: dict):
    if nombre == "iol":
        from src.broker.iol import IOLBroker
        return IOLBroker(_iol_client(), settings)
    from src.broker.paper import PaperBroker
    return PaperBroker(settings["portfolio"]["paper_capital_inicial_ars"])


def _analizar(settings, universe, horizonte, en_cartera=None):
    from src.data.fundamentals import load_fundamentals
    from src.pipeline import analyze, load_prices

    iol = _iol_client() if settings["datos"]["fuente_precios"] == "iol" else None
    print("Bajando precios y CCL...")
    usd, ultimo_ars = load_prices(universe, settings, iol)
    print("Bajando fundamentales...")
    fund = load_fundamentals(universe)
    res = analyze(usd, fund, universe, settings, horizonte, en_cartera)
    return res, ultimo_ars


def cmd_analizar(args, settings, universe):
    res, _ = _analizar(settings, universe, args.horizonte)
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"analisis_{args.horizonte}_{_stamp()}.csv"
    res.to_csv(out)
    print(f"\nRanking horizonte {args.horizonte} (USD CCL):\n")
    print(res.drop(columns=["en_cartera"]).to_string())
    print(f"\nGuardado en {out}\n{DESCARGO}")


def cmd_ordenes(args, settings, universe):
    from src.portfolio.rules import build_targets, generate_orders

    broker = _broker(args.broker, settings)
    posiciones, caja = broker.get_positions(), broker.get_cash_ars()
    res, ultimo_ars = _analizar(settings, universe, args.horizonte, set(posiciones))
    precios = {**{t: p["precio"] for t, p in posiciones.items() if p.get("precio")}, **ultimo_ars}

    total = caja + sum(p["cantidad"] * precios.get(t, 0) for t, p in posiciones.items())
    pesos_act = {t: p["cantidad"] * precios.get(t, 0) / total for t, p in posiciones.items()} if total else {}
    targets = build_targets(res[["score"]], pesos_act, sector_map(universe), settings)
    ordenes = generate_orders(targets, posiciones, caja, precios, settings)

    print(f"\nBroker: {broker.nombre} | Caja: ${caja:,.0f} | Valor total: ${total:,.0f}\n")
    print(res[["score", "senal", "score_tecnico", "score_fundamental"]].to_string())
    if ordenes.empty:
        print("\nNo hay órdenes sugeridas: la cartera ya está alineada con los objetivos.")
        return
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"ordenes_{_stamp()}.csv"
    ordenes.to_csv(out, index=False)
    print(f"\nÓrdenes sugeridas:\n\n{ordenes.to_string(index=False)}")
    print(f"\nGuardadas en {out}. Revisalas y después: python main.py ejecutar {out}\n{DESCARGO}")


def cmd_ejecutar(args, settings, universe):
    from src.portfolio.risk import RiskError, validate_orders

    try:
        ordenes = pd.read_csv(args.archivo)
    except (FileNotFoundError, pd.errors.EmptyDataError) as e:
        sys.exit(f"No pude leer las órdenes de {args.archivo}: {e}")
    try:
        ordenes = validate_orders(ordenes, settings)
    except RiskError as e:
        sys.exit(f"Bloqueado por límites de riesgo: {e}")
    if ordenes.empty:
        sys.exit("El archivo no tiene órdenes.")

    if args.live:
        if os.getenv("IOL_LIVE_TRADING") != "1":
            sys.exit("Modo real deshabilitado: poné IOL_LIVE_TRADING=1 en .env si de verdad querés operar.")
        broker = _broker("iol", settings)
    else:
        broker = _broker("paper", settings)

    print(f"\nModo: {'REAL (IOL)' if args.live else 'PAPER (simulado)'}\n")
    print(ordenes[["ticker", "lado", "cantidad", "precio_limite", "monto_ars"]].to_string(index=False))
    if args.live:
        if input("\nEscribí CONFIRMAR para enviar estas órdenes a IOL: ").strip() != "CONFIRMAR":
            sys.exit("Cancelado. No se envió nada.")

    for _, o in ordenes.iterrows():
        try:
            r = broker.place_order(o["ticker"], o["lado"], int(o["cantidad"]), float(o["precio_limite"]))
        except Exception as e:
            r = {"estado": "error", "mensaje": str(e)}
        print(f"  {o['lado']:8} {int(o['cantidad']):>6} {o['ticker']:6} @ {o['precio_limite']:>10,.2f} -> {r}")


def cmd_backtest(args, settings, universe):
    from src.backtest.engine import run_backtest
    from src.data.prices import load_ccl, load_history, to_usd

    desde = date.fromisoformat(args.desde)
    print("Bajando historia (yfinance) y CCL...")
    ccl = load_ccl(desde)
    usd = {}
    for a in universe:
        ars = load_history(a["ticker"], desde, fuente="yfinance")
        if not ars.empty:
            usd[a["ticker"]] = to_usd(ars, ccl)
    b = settings["backtest"]
    res = run_backtest(usd, b["top_n"], b["score_minimo"], b["costo_bps"])
    print(f"\nBacktest {res['desde']} -> {res['hasta']} (USD CCL, solo score técnico)\n")
    print(pd.DataFrame({"estrategia": res["estrategia"], "benchmark": res["benchmark"]}).to_string())
    REPORTS_DIR.mkdir(exist_ok=True)
    out = REPORTS_DIR / f"backtest_{_stamp()}.csv"
    res["curvas"].to_csv(out)
    print(f"\nCurvas guardadas en {out}. Rendimientos pasados no garantizan futuros.")


def cmd_login_test(args, settings, universe):
    from src.broker.iol import IOLBroker

    b = IOLBroker(_iol_client(), settings)
    pos = b.get_positions()
    print(f"Login OK. Acciones en cartera: {len(pos)} | Caja ARS disponible: ${b.get_cash_ars():,.0f}")


def main(argv=None):
    settings, universe = load_settings(), load_universe()
    ap = argparse.ArgumentParser(description="Analizador de portfolio de acciones argentinas")
    sub = ap.add_subparsers(dest="cmd", required=True)
    horizontes = list(settings["pesos_horizonte"])

    p = sub.add_parser("analizar"); p.add_argument("--horizonte", choices=horizontes, default=settings["horizonte_default"])
    p = sub.add_parser("ordenes"); p.add_argument("--horizonte", choices=horizontes, default=settings["horizonte_default"])
    p.add_argument("--broker", choices=["paper", "iol"], default="paper")
    p = sub.add_parser("ejecutar"); p.add_argument("archivo"); p.add_argument("--live", action="store_true")
    p = sub.add_parser("backtest"); p.add_argument("--desde", default="2018-01-01")
    sub.add_parser("login-test")

    args = ap.parse_args(argv)
    {"analizar": cmd_analizar, "ordenes": cmd_ordenes, "ejecutar": cmd_ejecutar,
     "backtest": cmd_backtest, "login-test": cmd_login_test}[args.cmd](args, settings, universe)


if __name__ == "__main__":
    main()
