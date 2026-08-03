# file_id: SOM-PS1-0964-v1.0.0 name: install_watchdog.ps1 description: Install the SoMaCo fleet watchdog as a Windows scheduled task — supervisor starts at logon and is restarted every 5 min if dead (atomic lock makes dupes harmless) project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [watchdog, windows, persistence, robustness] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
# install_watchdog.ps1 — OS-native fleet persistence. No chat session required.
$root = "D:\somacosf\outputs\prediction-market-analysis"
$py = "$root\.venv311\Scripts\python.exe"
$sup = "$root\scripts\supervisor.py"
$taskName = "SoMaCo-Fleet"

$action = New-ScheduledTaskAction -Execute $py -Argument "`"$sup`"" -WorkingDirectory $root
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn
$triggerRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggerLogon, $triggerRepeat `
    -Settings $settings -Description "SoMaCo trading fleet supervisor (singleton via atomic lock)" -Force | Out-Null
Write-Output "installed: $taskName (logon + 5min restart-if-dead)"
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
