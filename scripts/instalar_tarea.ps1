# LEGADO (solo uso local): en producción el operador corre en GitHub Actions (.github/workflows/operador.yml).
# Ver docs/DEPLOY.md. Si usás esto en la PC, no actives también la nube: serían dos operadores.
# Registra la tarea "AccionesAR - operador": análisis completo cada hora de 11:30 a 16:30, lunes a viernes.
# En cada pasada el operador decide solo si opera (feriados y mercado cerrado se chequean adentro).
# Para quitarla:  Unregister-ScheduledTask -TaskName "AccionesAR - operador" -Confirm:$false
$script = Join-Path $PSScriptRoot "tarea_operador.ps1"
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$dias = "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
$disparo = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $dias -At 11:30
$rep = New-ScheduledTaskTrigger -Once -At 11:30 -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Hours 5 -Minutes 1)
$disparo.Repetition = $rep.Repetition
$opciones = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "AccionesAR - operador" -Action $accion -Trigger $disparo -Settings $opciones `
    -Description "Operador automatico de cartera, analisis continuo (modo segun settings: paper por defecto)" -Force
Unregister-ScheduledTask -TaskName "AccionesAR - analisis semanal" -Confirm:$false -ErrorAction SilentlyContinue
