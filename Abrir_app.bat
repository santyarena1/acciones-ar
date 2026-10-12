@echo off
REM Abre el panel de inversion en el navegador (http://localhost:8501). Cerrar esta ventana apaga la app.
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py app
