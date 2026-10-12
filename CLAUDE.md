# Acciones AR — Analizador de portfolio de acciones argentinas

## Qué es
Software en Python que analiza acciones argentinas (BYMA, panel líder) con análisis técnico + fundamental,
asigna un score 0–100 por acción y por horizonte (corto / mediano / largo) y genera señales
(COMPRAR / AGREGAR / MANTENER / REDUCIR / VENDER) y **órdenes sugeridas** para un portfolio.

**No es un bot de trading.** Es un sistema de inversión de portfolio con rebalanceo periódico (semanal/mensual).

Dueño: Santy. Broker: **IOL (InvertirOnline)** vía API v2. Bull Market (Primary/pyRofex) podría sumarse después
como otro adaptador en `src/broker/`.

## Reglas no negociables
1. **Todo se analiza en dólares CCL.** Los precios en pesos están contaminados por inflación; cualquier
   indicador o métrica de rendimiento se calcula sobre la serie `precio_ARS / CCL`.
2. **La ejecución es determinística y la confirma un humano.** Ningún LLM (Grok, Claude ni otro) decide ni
   envía órdenes. El flujo es: `analizar` → `ordenes` (CSV) → revisión humana → `ejecutar`.
3. **Modo `paper` por defecto.** Operar en real requiere las tres cosas: `--live`, `IOL_LIVE_TRADING=1` en `.env`
   y escribir `CONFIRMAR` en la terminal. No relajar esto.
4. **Límites de riesgo duros** en `config/settings.yaml` (`riesgo:`): monto máximo por orden, órdenes máximas
   por corrida, órdenes siempre a precio límite. Se validan en `src/portfolio/risk.py` antes de cualquier envío.
5. **Nunca commitear `.env`** ni credenciales. Nunca loguear el token de IOL.
6. **Sin lookahead en el backtest.** Los indicadores son causales (rolling/ewm) y se leen en la fecha de
   rebalanceo. Los fundamentales actuales NO son point-in-time, por eso el backtest usa solo el score técnico
   (está aclarado en el reporte).

## Estructura
```
main.py                     CLI: analizar | ordenes | ejecutar | backtest | login-test
config/settings.yaml        pesos por horizonte, umbrales, límites de portfolio y riesgo
config/universe.yaml        universo (ticker, sector, ADR y ratio para fundamentales/CCL)
data/fundamentals_manual.csv  overrides manuales de fundamentales (pisan a yfinance)
src/config.py               carga de configuración
src/broker/base.py          interfaz Broker (posiciones, caja, enviar orden)
src/broker/iol.py           cliente API IOL v2 (token + refresh) y IOLBroker
src/broker/paper.py         broker simulado con estado en data/paper_state.json
src/data/prices.py          históricos (yfinance o IOL), CCL histórico, conversión a USD, caché
src/data/fundamentals.py    métricas fundamentales (yfinance de los ADR + CSV manual)
src/analysis/technical.py   indicadores (SMA, EMA, RSI, MACD, momentum, volatilidad) y score técnico
src/analysis/fundamental.py score fundamental (calidad, valuación, salud financiera, crecimiento)
src/analysis/scoring.py     combinación por horizonte y señales
src/portfolio/rules.py      pesos objetivo (topes por acción/sector, caja mínima) y órdenes
src/portfolio/risk.py       validación de órdenes contra límites de riesgo
src/backtest/engine.py      backtest de rebalanceo mensual vs. buy & hold equiponderado (USD)
src/pipeline.py             orquesta datos → análisis → tabla de resultados
tests/                      tests con datos sintéticos (no usan red)
reports/                    salidas CSV (gitignored)
```

## Comandos
```bash
pip install -r requirements.txt
cp .env.example .env            # completar IOL_USERNAME / IOL_PASSWORD
python main.py login-test       # verifica credenciales IOL
python main.py analizar --horizonte mediano
python main.py ordenes --horizonte mediano --broker paper
python main.py ejecutar reports/ordenes_YYYYMMDD_HHMM.csv           # paper
python main.py backtest --desde 2018-01-01
pytest -q
```

## API de IOL (verificar contra https://api.invertironline.com antes de tocar)
- Token: `POST /token` form `grant_type=password&username=&password=`; refresh con `grant_type=refresh_token`.
- Cotización: `GET /api/v2/{mercado}/Titulos/{simbolo}/Cotizacion`
- Histórico: `GET /api/v2/{mercado}/Titulos/{simbolo}/Cotizacion/seriehistorica/{desde}/{hasta}/{ajustada|sinAjustar}`
- Portafolio: `GET /api/v2/portafolio/argentina` · Estado de cuenta: `GET /api/v2/estadocuenta`
- Órdenes: `POST /api/v2/operar/Comprar` y `/Vender` (mercado, simbolo, cantidad, precio, plazo, validez, tipoOrden)
- Mercado BYMA = `bCBA`. Los nombres exactos de campos de respuesta se parsean de forma defensiva en
  `src/broker/iol.py`; si IOL cambia algo, arreglarlo ahí y en sus tests.

## Pendientes / ideas (en orden sugerido)
- [ ] Validar parsers de IOL con respuestas reales y guardar fixtures anonimizados en `tests/fixtures/`.
- [ ] Verificar ratios de ADR en `universe.yaml` (cambian con los años).
- [ ] Fundamentales point-in-time (balances trimestrales de CNV) para poder backtestear el score completo.
- [ ] Score de momentum relativo (percentil vs. universo) además del absoluto.
- [ ] Contexto macro: riesgo país, brecha cambiaria, tasa — como ajuste del % de caja.
- [ ] Sumar CEDEARs como universo opcional.
- [ ] Dashboard (Streamlit o HTML) con el ranking y la cartera.
- [ ] Adaptador Bull Market vía Primary API (pyRofex) implementando `Broker`.

## Estilo
- Python 3.11+, type hints, funciones puras en `analysis/` (sin red, sin I/O) para que sean testeables.
- Comentarios y mensajes de CLI en español rioplatense.
- Cualquier umbral nuevo va a `settings.yaml`, no hardcodeado.
- Antes de cerrar un cambio: `pytest -q` en verde.

## Descargo
Herramienta de análisis personal. No es asesoramiento financiero; las decisiones de inversión son del usuario.
