# Acciones AR — Operador automático de inversiones (IOL)

## Qué es
Sistema en Python que administra una cartera en IOL (InvertirOnline): analiza acciones argentinas (panel líder y
general), CEDEARs, bonos soberanos en dólares, ONs, Lecaps/Boncaps y bonos CER; arma la cartera objetivo según el
perfil del dueño y el contexto macro, y **opera solo** (compra y vende) cuando el análisis lo justifica.
Corre en la nube: web en Vercel (Next.js, carpeta `web/`, la hace otro ingeniero) + motor Python en GitHub
Actions, unidos SOLO por una base Postgres (Neon). Nada depende de la PC del dueño. La app Streamlit (`app/`) queda
como legado para uso local.

Dueño: Santy (no programa: todo lo que ve el usuario va en castellano llano, sin nombres internos).

## Reglas no negociables
1. **Todo se analiza en dólares.** Locales: precio ARS / CCL. CEDEARs: precio del subyacente en USD.
2. **Las decisiones de compra/venta son determinísticas** (motor cuantitativo). Ningún LLM decide ni envía órdenes.
3. **Operación automática autorizada por el dueño (2026-10-11).** Modo real exige las dos cosas:
   preferencia `operador.modo: live` (tabla `preferencias`, o `data/usuario.yaml` en local) **y** una habilitación
   explícita: estado `modo_real` = `{habilitado: true}` (lo pone el dueño desde la web con sesión iniciada) o
   `IOL_LIVE_TRADING=1` en el `.env` local. Fuera de horario, aun forzada, una corrida en modo real solo analiza.
   Por defecto: práctica (paper). Claude nunca activa el modo real, nunca carga credenciales y nunca corre
   `operar --modo live`.
4. **Sin topes de estrategia** (decisión del dueño), pero **sí protecciones técnicas** contra datos rotos y bugs:
   no repetir órdenes en el día (bitácora + operaciones del broker), precio en vivo dentro de tolerancia, compras
   nunca mayores a la caja disponible (ventas liquidan T+1), ninguna orden > `riesgo.orden_maxima_pct_cartera`,
   candado entre corridas, calendario de feriados obligatorio. No relajar estas protecciones.
5. **Nunca commitear `.env` ni `data/`.** Nunca loguear token, usuario ni clave de IOL o Telegram. El repo y los
   logs de Actions son públicos: en la nube la CLI corre con `SALIDA_SILENCIOSA=1` (solo líneas genéricas, sin
   montos, tickers ni errores); el detalle va a la tabla `eventos`.
6. **Sin lookahead en el backtest.** Fundamentales actuales no son point-in-time: el backtest usa solo técnico.
7. **Evidencia antes que opinión**: un cambio de estrategia se justifica con backtest en subperíodos, sin sobreajustar.

## Cómo funciona
- **Nube**: `.github/workflows/operador.yml` corre cada hora a las :30 de 11:30 a 16:30 (hora Argentina), lunes a
  viernes, y a mano (`workflow_dispatch`, botón "Revisar ahora" de la web, con `forzar`). Pasos: `db-init`
  (idempotente) → `reportes` (lunes y martes) → `operar`. Secrets de GitHub: solo `DATABASE_URL` y `CLAVE_CIFRADO`.
  `concurrency: operador` evita corridas superpuestas (además del candado en la base). Paso a paso: `docs/DEPLOY.md`.
- **Base** (`db/schema.sql` = contrato con la web; `src/db.py` = SQLAlchemy Core): con `DATABASE_URL` todo se guarda
  ahí (bitácora/estado, corridas, cartera de práctica, preferencias, reportes semanales, pedidos de la web). Sin
  `DATABASE_URL`, todo sigue en archivos locales (desarrollo y tests).
- **Claves**: IOL y Telegram están cifradas en la tabla `secretos` (AES-256-GCM, compatible con la web;
  `src/secretos.py`, vector en `db/vector_cifrado.json`). Se descifran al empezar cada comando.
- `src/servicio.py::correr` — corrida completa: reporte semanal → precios/CCL/macro → fundamentales → scores →
  asignación por clase (perfil + régimen macro) → objetivos (acciones/CEDEARs + renta fija) → órdenes → guía.
- `src/operador/ejecutor.py::operar` — un ciclo: candado → pedidos de la web (`comandos.py`) → pausa/horario →
  cancela pendientes viejas → `correr` contra la cartera real del broker → decide (salidas y entradas siempre,
  ajustes solo si superan `operador.banda_no_operar`) → protecciones → ventas y compras a precio límite → bitácora
  → pedido de fondos → resumen diario por Telegram en la última corrida (`resumen.py`).
- Reportes semanales: el PDF nunca se guarda; se persiste todo lo extraído (tabla `reportes`) y se borra el PDF.
- Estrategia por clase: acciones argentinas → cartera pareja de las más líquidas del panel líder (el modelo técnico
  no le ganó a eso en el backtest 2018–2026); CEDEARs → score técnico+fundamental (sí le ganó); renta fija →
  mejores por `score_rf` con filtro de calidad de datos.
- Legado local: `scripts/*.ps1` (tarea programada de Windows) y `app/` (Streamlit). No usar junto con la nube.

## Estructura
```
main.py                       CLI: db-init | operar | reportes | analizar | ejecutar | backtest | login-test | app
.github/workflows/            operador.yml (cron + manual) y tests.yml
db/schema.sql                 esquema Postgres (contrato con la web); db/vector_cifrado.json (prueba de cifrado)
docs/DEPLOY.md                puesta en marcha en la nube, paso a paso
app/                          app web (Streamlit). app.py navegación; paginas/*; etiquetas.py (nombres legibles);
                              credenciales.py (.env: IOL, Telegram, modo real)
config/settings.yaml          parámetros (umbrales, perfiles, macro, liquidez, riesgo, operador)
config/universe.yaml          universo: lider / general / cedears
config/renta_fija.yaml        términos de bonos y letras (con fuente y confianza)
data/usuario.yaml             preferencias elegidas en la app (pisan settings.yaml)
data/operador/                bitácora (jsonl) y estado del operador (solo sin base de datos)
src/db.py, src/secretos.py    base de datos (SQLAlchemy Core) y claves cifradas
src/salida.py                 modo silencioso para los logs públicos
src/analysis/                 técnico, fundamental, relativo (percentiles), macro, scoring (señales, histéresis);
                              capa táctica: riesgo_global, rotacion, eventos, tactico (config/eventos.yaml)
src/portfolio/                rules (objetivos por clase), orders, risk (validación), renta_fija_alloc
src/renta_fija/               valuación de bonos/letras (TIR, duration, curvas, calidad de datos)
src/data/                     precios (yfinance, argentinadatos), fundamentales, reporte Gorostiaga
src/broker/                   IOL (cliente + parsers) y paper (simulado)
src/operador/                 ejecutor, decisión, mercado (horario BYMA), bitácora (+ bitacora_db), comandos de la
                              web, resumen diario, notificaciones
src/backtest/engine.py        backtest mensual en USD; tactico.py multi-activo 2008-2026 (perfil vs. capa táctica)
src/guia.py, src/store.py     explicación en lenguaje llano; corridas (tabla corridas, o reports/corridas/)
tests/                        sin red (fixtures)
```

## Comandos
```bash
.venv/Scripts/python main.py app                       # app web (o doble click en Abrir_app.bat)
.venv/Scripts/python main.py operar --forzar-horario   # un ciclo del operador en el modo configurado
.venv/Scripts/python main.py db-init                   # aplica db/schema.sql (necesita DATABASE_URL)
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
- [x] Motor en la nube (GitHub Actions + Neon) y resumen diario por Telegram.
- [ ] Web en Vercel (Next.js, `web/`): login, preferencias, habilitar modo real, pedidos, claves cifradas.
- [ ] Bot de Telegram con comandos (/estado /cartera /pausar /reanudar).
- [ ] Tick size de BYMA en precios límite.

## Descargo
Herramienta personal. No es asesoramiento financiero; las decisiones y el riesgo son del dueño.
