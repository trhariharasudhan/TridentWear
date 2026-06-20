@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0..\.."

echo ===================================================
echo   TridentWear Local Development Server Launcher
echo ===================================================
echo.

echo Checking Python environment...
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ERROR: Virtual environment not found.
    echo.
    echo Expected:
    echo %cd%\.venv\Scripts\python.exe
    echo.
    echo Create or restore the virtual environment first.
    echo.
    pause
    exit /b 1
)

echo Checking available local ports...
set "PORTS=8020,8021,8022,8023,8030"

rem Call powershell to find the first available port from the candidate list
powershell -NoProfile -Command "$ports = @(8020, 8021, 8022, 8023, 8030); $selected = $null; foreach ($p in $ports) { try { $l = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $p); $l.Start(); $l.Stop(); $selected = $p; break; } catch { Write-Host 'Port '$p' is occupied. Trying next...' -ForegroundColor Yellow } }; if ($selected) { Out-File -FilePath .selected_port.tmp -InputObject $selected -Encoding ascii } else { exit 1 }"

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: No available local development port was found.
    echo Checked: 8020, 8021, 8022, 8023, 8030
    echo.
    pause
    exit /b 1
)

set /p SELECTED_PORT=<.selected_port.tmp
del .selected_port.tmp

echo.
echo Selected port: %SELECTED_PORT%
echo Starting TridentWear...
echo.
echo Website URL:
echo http://127.0.0.1:%SELECTED_PORT%/
echo.
echo Press CTRL+C to stop the server.
echo.

rem Start a background process to open browser once the server is ready (health check returns 200)
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 1; 1..15 | ForEach-Object { try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:%SELECTED_PORT%/health' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { Start-Process 'http://127.0.0.1:%SELECTED_PORT%/'; exit } } catch {} ; Start-Sleep -Seconds 1 }"

rem Run Uvicorn attached to terminal
set PYTHONPATH=backend
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port %SELECTED_PORT% --reload

if %ERRORLEVEL% neq 0 (
    echo.
    echo Server stopped or failed to start with exit code %ERRORLEVEL%.
    pause
)
