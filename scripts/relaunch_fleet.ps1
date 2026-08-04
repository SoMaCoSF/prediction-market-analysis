# file_id: SOM-PS-0109-v1.0.0 name: relaunch_fleet.ps1 description: Post-reboot fleet + deploy helper. Confirms the auto-started fleet, and provides a RAM-safe Vercel deploy that does NOT OOM (sets Node old-space to 8GB). Run from PowerShell after reboot + Hermes relaunch. project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [relaunch, reboot, deploy, vercel, oom] created: 2026-08-04 version: 1.0.0 agent_id: HERMES-AGENT
<#
  relaunch_fleet.ps1 — run AFTER reboot + Hermes relaunch.
  The fleet auto-starts via Registry Run (SoMaCoFleet) on login.
  This script verifies it, and gives you a RAM-safe deploy.

  USAGE:
    powershell -ExecutionPolicy Bypass -File relaunch_fleet.ps1          # just check fleet
    powershell -ExecutionPolicy Bypass -File relaunch_fleet.ps1 -Deploy   # check + deploy trading app
    powershell -ExecutionPolicy Bypass -File relaunch_fleet.ps1 -DeployPlatform
#>
param([switch]$Deploy, [switch]$DeployPlatform)

$ErrorActionPreference = 'SilentlyContinue'

# --- 1. confirm fleet ---
$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'scripts/supervisor\.py' }
if ($procs) {
    Write-Output "FLEET SUPERVISOR ALIVE: PIDs $($procs.ProcessId -join ', ')"
} else {
    Write-Output "FLEET NOT AUTO-STARTED — launching supervisor manually..."
    $py = "D:\somacosf\outputs\prediction-market-analysis\.venv311\Scripts\pythonw.exe"
    $sup = "D:\somacosf\outputs\prediction-market-analysis\scripts\supervisor.py"
    Start-Process -FilePath $py -ArgumentList $sup -WindowStyle Hidden
    Start-Sleep -Seconds 20
}

# --- 2. show heartbeat count from ledger (proves daemons up) ---
$ledger = & "D:\somacosf\outputs\prediction-market-analysis\.venv311\Scripts\python.exe" -c "
import sys; sys.path.insert(0,'D:/somacosf/outputs/prediction-market-analysis/scripts')
import sb
c=sb.sb_conn(); cur=c.cursor()
cur.execute(\"SELECT count(*) FROM mc_state WHERE k LIKE 'daemon:%' AND extract(epoch from now()-updated_at) < 400\")
print('alive daemons (heartbeat <400s):', cur.fetchone()[0])
c.close()
"
Write-Output $ledger

# --- 3. RAM-safe deploy (the OOM fix: 8GB old-space) ---
if ($Deploy -or $DeployPlatform) {
    $env:NODE_OPTIONS = "--max-old-space-size=8192"
    if ($Deploy) {
        Write-Output "Deploying TRADING app (time/trade/poly + /status) ..."
        Set-Location "D:\somacosf\outputs\prediction-market-analysis"
    } else {
        Write-Output "Deploying PLATFORM app (about/login/nav) ..."
        Set-Location "D:\somacosf\outputs\somacosf-platform"
    }
    & vercel --prod --yes 2>&1 | Select-String -Pattern "Ready|error|Error|FATAL" | Select-Object -First 6
    Write-Output "Deploy done. Verify: https://time.somacosf.com/status  (expect 200)"
}
