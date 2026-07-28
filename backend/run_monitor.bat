@echo off
title SafeWatch Monitor
cd /d "%~dp0"

echo ==============================================
echo   SafeWatch Monitor - starting server...
echo   The dashboard will open automatically at:
echo   http://localhost:8001/
echo.
echo   To stop: press Ctrl+C or close this window.
echo ==============================================
echo.

rem Open the dashboard a few seconds after the server starts
start "" /min cmd /c "timeout /t 6 >nul & start http://localhost:8001/"

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8001

echo.
echo Server stopped.
pause
