# Acciones AR

Analizador de portfolio de acciones argentinas (panel líder BYMA): score técnico + fundamental en USD CCL,
señales por horizonte y órdenes sugeridas. Ejecución en modo simulado por defecto; real vía API de IOL con
triple confirmación.

## Arranque rápido
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # completar usuario/clave de IOL
pytest -q
python main.py analizar --horizonte mediano
python main.py ordenes --broker paper
python main.py backtest --desde 2018-01-01
```

## Habilitar la API de IOL
Desde tu cuenta: consulta → Tipo "Mi cuenta" → Razón "Api". Cuando esté activa: `python main.py login-test`.

## Con Claude Code
Abrí la carpeta con `claude`. El contexto del proyecto está en `CLAUDE.md`. Comandos:
`/analizar mediano`, `/revisar-ordenes`, `/nueva-metrica <descripción>`.
Claude Code tiene bloqueado `ejecutar --live` y leer `.env` (ver `.claude/settings.json`).

> Herramienta de análisis personal. No es asesoramiento financiero.
