@echo off
REM ============================================================
REM  SafeWatch - first time setup (run once per PC)
REM  ASCII only - Korean text breaks cmd parsing on some systems
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo [1/3] Creating virtual environment...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 goto :fail
) else (
    echo      already exists - skipping
)

echo.
echo [2/3] Installing dependencies...
.venv\Scripts\python.exe -m pip install -q -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo [3/3] Building keyword score dictionary...
echo      (skipping this makes every article go to Gemini - big cost increase)
if exist "app\data\keyword_scores.json" (
    echo      already exists - skipping
) else (
    .venv\Scripts\python.exe build_keyword_scores.py
    if errorlevel 1 (
        echo.
        echo  *** WARNING: keyword dictionary was NOT built. ***
        echo  The app will still run, but every article goes to Gemini.
        echo  Locate the source file and run:
        echo      .venv\Scripts\python.exe build_keyword_scores.py --xlsx "PATH\keyword.xlsx"
        echo.
    )
)

echo.
echo ============================================================
echo  Setup done.
echo   - Put SUPABASE / GEMINI keys in backend\.env
echo   - Apply database\migrations\*.sql in Supabase SQL Editor
echo   - Start with run_monitor.bat
echo  Check http://localhost:8001/api/health -> "prefilter.enabled"
echo ============================================================
pause
exit /b 0

:fail
echo.
echo  Setup FAILED. See the error above.
pause
exit /b 1
