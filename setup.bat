@echo off
setlocal
cd /d "%~dp0"
echo.
echo  === Ops Center setup (no admin rights needed) ===
echo.

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

%PY% -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>nul
if errorlevel 1 (
  echo  [!] This needs Python 3.11, 3.12 or 3.13 - 3.13 is the best choice.
  echo      Your version:
  %PY% --version
  echo      Install 3.13 from python.org ^(per-user install, no admin needed^), then run setup.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo  Creating the project's own Python environment in .venv ...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

echo  Installing packages ...
if exist wheelhouse (
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements.txt
) else (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if errorlevel 1 goto :fail

".venv\Scripts\python.exe" scripts\init_env.py
echo.
echo  Done! Now double-click run.bat
pause
exit /b 0

:fail
echo.
echo  [!] Setup failed - read the messages above. Ask your mentor.
pause
exit /b 1
