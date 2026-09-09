@echo off
setlocal
cd /d %~dp0
echo ================================================
echo   AI Daily News Workflow - first-time setup
echo ================================================
set "PYEXE=python"
where py >nul 2>nul && set "PYEXE=py -3"
echo [1/3] Creating virtual environment (.venv) ...
%PYEXE% -m venv .venv
if errorlevel 1 goto :fallback
set "VPY=.venv\Scripts\python.exe"
echo [2/3] Installing dependencies ...
"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
if not exist .env copy .env.example .env >nul
echo [3/3] Done.
echo.
echo Next steps:
echo   1) edit ".env" - configure DeepSeek API key OR your local model service
echo   2) double-click "menu.bat" and choose [6] Status to check
echo   3) choose [1] to generate today's news
echo   4) see README.md for fixed cover and Chrome login setup
pause
exit /b 0
:fallback
echo Note: venv creation failed; will use system python instead.
if not exist .env copy .env.example .env >nul
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo Done (system python). Use "menu.bat".
pause
exit /b 0
:fail
echo Setup failed - check Python 3.10+ and internet, then run setup.bat again.
pause
exit /b 1