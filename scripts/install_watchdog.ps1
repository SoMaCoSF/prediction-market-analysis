# file_id: SOM-PS1-0964-v1.1.0 name: install_watchdog.ps1 description: Install the SoMaCo fleet watchdog via schtasks.exe — supervisor starts at logon + 5-min restart-if-dead task (atomic lock makes dupes harmless) project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [watchdog, windows, persistence, robustness] created: 2026-08-03 modified: 2026-08-03 version: 1.1.0 agent_id: HERMES-AGENT
# install_watchdog.ps1 — OS-native fleet persistence (schtasks.exe path — reliable).
$root = "D:\somacosf\outputs\prediction-market-analysis"
$py = "$root\.venv311\Scripts\python.exe"
$sup = "$root\scripts\supervisor.py"
$tr = "`"$py`" `"$sup`""

schtasks /Create /TN "SoMaCo-Fleet" /TR $tr /SC ONLOGON /RL LIMITED /F | Out-Null
schtasks /Create /TN "SoMaCo-Fleet-Watch" /TR $tr /SC MINUTE /MO 5 /RL LIMITED /F | Out-Null

Write-Output "installed: SoMaCo-Fleet (logon) + SoMaCo-Fleet-Watch (every 5 min)"
schtasks /Query /TN "SoMaCo-Fleet" /FO LIST | Select-String "TaskName|Status"
schtasks /Query /TN "SoMaCo-Fleet-Watch" /FO LIST | Select-String "TaskName|Status"
