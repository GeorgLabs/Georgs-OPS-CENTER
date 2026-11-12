@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo  Run setup.bat first.
  pause
  exit /b 1
)
if not exist ".env" (
  echo  Run setup.bat first - the .env file is missing.
  pause
  exit /b 1
)
echo.
echo  Ops Center is starting at http://127.0.0.1:8001  ^(Ctrl+C stops it^)
echo  The server restarts by itself whenever you save a .py file.
echo.
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8001"
".venv\Scripts\python.exe" -m fastapi dev --port 8001
pause
