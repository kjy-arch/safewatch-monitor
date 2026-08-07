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

rem A/B 전용 PC의 로컬 브라우저만 접속할 수 있게 loopback에 바인딩한다.
rem LAN/서버 배포는 인증을 추가한 뒤 별도 실행 설정으로 구성해야 한다.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8001

echo.
echo Server stopped.
pause
