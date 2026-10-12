# Acciones AR — Operador automático de inversiones (IOL)

## Qué es
Sistema en Python que administra una cartera en IOL (InvertirOnline): analiza acciones argentinas (panel líder y
general), CEDEARs, bonos soberanos en dólares, ONs, Lecaps/Boncaps y bonos CER; arma la cartera objetivo según el
perfil del dueño y el contexto macro, y **opera solo** (compra y vende) cuando el análisis lo justifica.
App web local (Streamlit) para ver todo y configurar. Más adelante: Vercel + bot de Telegram.

Dueño: Santy (no programa: todo lo que ve el usuario va en castellano llano, sin nombres internos).

## Reglas no negociables
1. **Todo se analiza en dólares.** Locales: precio ARS / CCL. CEDEARs: precio del subyacente en USD.
2. **Las decisiones de compra/venta son determinísticas** (motor cuantitativo). Ningún LLM decide ni envía órdenes.
3. **Operación automática autorizada por el dueño (2026-10-11).** Modo real exige las dos cosas:
   `operador.modo: live` (se elige en Configuración de la app, queda en `data/usuario.yaml`) **y**
   `IOL_LIVE_TRADING=1` en `.env`. Por defecto: práctica (paper). Claude nunca activa el modo real, nunca carga
   credenciales y nunca corre `operar --modo live`.
4. **Sin topes de estrategia** (decisión del dueño), pero **sí protecciones técnicas** contra datos rotos y bugs:
   no repetir órdenes en el día (bitácora + operaciones del broker), precio en vivo dentro de tolerancia, compras
   nunca mayores a la caja disponible (ventas liquidan T+1), ninguna orden > `riesgo.orden_maxima_pct_cartera`,
   candado entre corridas, calendario de feriados obligatorio. No relajar estas protecciones.
5. **Nunca commitear `.env` ni `data/`.** Nunca loguear token, usuario ni clave de IOL o Telegram.
6. **Sin lookahead en el backtest.** Fundamentales actuales no son point-in-time: el backtest usa solo técnico.
7. **Evidencia antes que opinión**: un cambio de estrategia se justifica con backtest en subperíodos, sin sobreajustar.

## Cómo funciona
- `src/servicio.py::correr` — corrida completa: reporte semanal → precios/CCL/macro → fundamentales → scores →
  asignación por clase (perfil + régimen macro) → objetivos (acciones/CEDEARs + renta fija) → órdenes → guía.
- `src/operador/ejecutor.py::operar` — un ciclo del operador: pausa/horario → cancela pendientes viejas → `correr`
  contra la cartera real del broker → decide (salidas y entradas siempre, ajustes solo si superan
  `operador.banda_no_operar`) → protecciones → envía ventas y compras a precio límite → bitácora → pedido de fondos.
- Tarea programada de Windows "AccionesAR - operador": cada 15 min, 11:05–16:55, lunes a viernes
  (`scripts/instalar_tarea.ps1`). Logs en `reports/logs/`.
- Estrategia por clase: acciones argentinas → cartera pareja de las más líquidas del panel líder (el modelo técnico
  no le ganó a eso en el backtest 2018–2026); CEDEARs → score técnico+fundamental (sí le ganó); renta fija →
  mejores por `score_rf` con filtro de calidad de datos.

## Estructura
```
main.py                       CLI: app | analizar | operar | ejecutar | backtest | reportes | login-test
app/                          app web (Streamlit). app.py navegación; paginas/*; etiquetas.py (nombres legibles);
                              credenciales.py (.env: IOL, Telegram, modo real)
config/settings.yaml          parámetros (umbrales, perfiles, macro, liquidez, riesgo, operador)
config/universe.yaml          universo: lider / general / cedears
config/renta_fija.yaml        términos de bonos y letras (con fuente y confianza)
data/usuario.yaml             preferencias elegidas en la app (pisan settings.yaml)
data/operador/                bitácora (jsonl) y estado del operador
src/analysis/                 técnico, fundamental, relativo (percentiles), macro, scoring (señales, histéresis);
                              capa táctica: riesgo_global, rotacion, eventos, tactico (config/eventos.yaml)
src/portfolio/                rules (objetivos por clase), orders, risk (validación), renta_fija_alloc
src/renta_fija/               valuación de bonos/letras (TIR, duration, curvas, calidad de datos)
src/data/                     precios (yfinance, argentinadatos), fundamentales, reporte Gorostiaga
src/broker/                   IOL (cliente + parsers) y paper (simulado)
src/operador/                 ejecutor, decisión, mercado (horario BYMA), bitácora, notificaciones
src/backtest/engine.py        backtest mensual en USD; tactico.py multi-activo 2008-2026 (perfil vs. capa táctica)
src/guia.py, src/store.py     explicación en lenguaje llano; corridas guardadas en reports/corridas/
tests/                        sin red (fixtures)
```

## Comandos
```bash
.venv/Scripts/python main.py app                       # app web (o doble click en Abrir_app.bat)
.venv/Scripts/python main.py operar --forzar-horario   # un ciclo del operador en el modo configurado
.venv/Scripts/python main.py analizar                  # análisis sin operar
.venv/Scripts/python main.py backtest --universo cedears --desde 2018-01-01
.venv/Scripts/python main.py backtest-tactico          # perfil fijo vs. régimen AR / riesgo global / rotación
.venv/Scripts/python -m pytest -q
```
Python: `py -3.13` (no hay `python` en PATH). Venv en `.venv`.

## API de IOL
Ver `src/broker/iol.py` (endpoints confirmados contra el swagger público). Bonos/letras/ONs: `cantidad` en VN y
`precio` cada 100 VN. Pendiente de verificar con credenciales reales: casing de `titulo.tipo`, `saldos` del estado
de cuenta, respuesta de `operar` (numeroOperacion), ticker con que la cartera lista bonos/ONs, `laminaMinima`.

## Pendientes
- [ ] Verificar IOL con cuenta real (lectura) apenas el dueño cargue credenciales.
- [ ] Bot de Telegram (comandos /estado /cartera /pausar /reanudar /reporte + resumen diario) — al pasar a Vercel.
- [ ] Vercel: UI en Next.js + funciones Python + cron + base de datos + login.
- [ ] Tick size de BYMA en precios límite.

## Descargo
Herramienta personal. No es asesoramiento financiero; las decisiones y el riesgo son del dueño.
