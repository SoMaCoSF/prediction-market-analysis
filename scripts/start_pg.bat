@echo off
REM scripts/start_pg.bat  — no-admin startup for local Postgres + 4242 viewer
REM Run from the project root:  prediction-market-analysis\scripts\start_pg.bat
REM (or call with full path). Brings up the UUID engine + viewer after a reboot.

SETLOCAL
SET "ROOT=%~dp0.."
SET "PGDIR=%ROOT%\.pg\pg16\pgsql"
SET "DATA=%ROOT%\.pg\data"
SET "LOG=%ROOT%\.pg\logfile"
SET "VENV=%ROOT%\.venv311\Scripts\python.exe"
SET "PGPASSWORD=hermes_pg_2026"

REM 1) start postgres if not already listening on 5432
"%PGDIR%\bin\pg_ctl.exe" -D "%DATA%" status >nul 2>&1
IF ERRORLEVEL 1 (
    echo [start_pg] launching postgres...
    start "" "%PGDIR%\bin\pg_ctl.exe" -D "%DATA%" -l "%LOG%" -o "-p 5432" start
    timeout /t 4 >nul
) ELSE (
    echo [start_pg] postgres already running
)

REM 2) start the viewer (background, own window)
echo [start_pg] launching viewer on http://localhost:4242
start "" "%VENV%" "%ROOT%\scripts\server_view.py"

echo [start_pg] done. Open http://localhost:4242
ENDLOCAL
