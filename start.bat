@echo off
setlocal
cd /d "%~dp0"
echo Starting TridentWear at http://127.0.0.1:8010
echo Run from project root using .venv
echo.
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8010
echo.
echo Server stopped or failed to start. Review the message above.
pause
