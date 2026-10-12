# Un ciclo del operador automático. El modo (paper/live) sale de config/settings.yaml -> operador.modo;
# el modo real además exige IOL_LIVE_TRADING=1 en el .env. Los martes baja antes el reporte de Gorostiaga.
$ErrorActionPreference = "Continue"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$logs = Join-Path $raiz "reports\logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs ("operador_{0:yyyyMMdd_HHmm}.log" -f (Get-Date))
$py = Join-Path $raiz ".venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"

"=== $(Get-Date) ===" | Out-File $log -Encoding utf8
# el reporte semanal sale lunes a última hora o martes: se busca esos días (si ya está bajado, no hace nada)
if ((Get-Date).DayOfWeek -in "Monday", "Tuesday") { & $py main.py reportes *>> $log }
& $py main.py operar *>> $log
"=== fin, código $LASTEXITCODE ===" | Out-File $log -Append -Encoding utf8

Get-ChildItem $logs -Filter "operador_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 60 |
    Remove-Item -Confirm:$false
