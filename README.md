# Acciones AR — operador automático de inversiones para IOL

Sistema en Python que administra una cartera en **IOL (InvertirOnline)**: analiza acciones argentinas, CEDEARs,
bonos soberanos en dólares, obligaciones negociables, Lecaps/Boncaps y bonos CER; arma una cartera según un perfil
de riesgo y **opera solo** cuando su análisis lo justifica, con protecciones técnicas (sin órdenes duplicadas,
precio en vivo dentro de tolerancia, nunca más compras que caja disponible, calendario de feriados BYMA).

> ⚠️ Herramienta de análisis personal. **No es asesoramiento financiero.** Invertir implica riesgo de pérdida.
> Rendimientos pasados (incluidos los backtests de este repo) no garantizan resultados futuros.

## Qué hace
- **Análisis** en dólares (locales: precio / CCL; CEDEARs: subyacente en USD): técnico y fundamental, absoluto y
  relativo al universo; renta fija con TIR, duration, curvas, valor relativo y filtro de calidad de datos.
- **Cartera por clase de activo** según perfil (conservador / moderado / medio agresivo / agresivo), escalada al
  capital disponible; efectivo sobrante estacionado en Lecap corta.
- **Operador**: corre cada hora con el mercado abierto, decide si operar, detecta depósitos, se compara contra
  "no hacer nada" (S&P 500 + Merval) y avisa caídas fuertes. Modo práctica por defecto.
- **Contexto**: reporte semanal de Gorostiaga Bursátil (macro, precios objetivo, eventos), riesgo global, rotación
  de sectores y calendario de eventos (informativos: en el backtest 2008–2026 no mejoraron el resultado).
- **App web** (Streamlit) en castellano: inicio, cartera, oportunidades, historial y configuración.

## Uso
```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q
.venv/Scripts/python main.py app            # app web en http://localhost:8501
.venv/Scripts/python main.py operar --forzar-horario   # un ciclo del operador (modo práctica)
.venv/Scripts/python main.py backtest --universo cedears --desde 2018-01-01
```
En producción corre en la nube: web en Vercel + motor en GitHub Actions + base Postgres (Neon). Ver
[docs/DEPLOY.md](docs/DEPLOY.md). Las claves de IOL y Telegram se cargan desde la web y quedan cifradas en la base.
En local (sin `DATABASE_URL`) todo vive en archivos y `.env` (ver `.env.example`). El modo real requiere
activarlo explícitamente.

## Evidencia (backtests en USD, con costos; sesgo de supervivencia: universo actual)
| Parte | Estrategia | Resultado 2018–2026 |
|---|---|---|
| CEDEARs | score técnico + fundamental | 27,8% anual vs 21,4% equiponderado |
| Acciones AR | 8 más líquidas del panel líder, equiponderadas | 9,0% anual (el score perdía: −0,7%) |

Detalle de arquitectura y reglas en [CLAUDE.md](CLAUDE.md).
