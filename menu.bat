@echo off
setlocal enabledelayedexpansion
cd /d %~dp0
chcp 65001 >nul

rem ---- pick python: project venv -> py -3 -> python ----
if exist ".venv\Scripts\python.exe" (
    set "PYEXE=.venv\Scripts\python.exe"
    set "PYOPTS="
) else (
    where py >nul 2>nul && (set "PYEXE=py" & set "PYOPTS=-3") || (set "PYEXE=python" & set "PYOPTS=")
)

:menu
cls
echo ================================================
echo        AI Daily News Workflow
echo ================================================
echo   [1] Generate today (crawl + AI writing)
echo   [2] Open review folder
echo   [3] Select a review file and save to WeChat drafts (local browser)
echo   [4] Enable daily auto (09:00) + keep scheduler on
echo   [5] Disable daily auto
echo   [6] Status
echo   [0] Exit
echo ================================================
set "CMD="
set /p CMD=Choose [0-6]: 
if "!CMD!"=="1" goto gen
if "!CMD!"=="2" goto open
if "!CMD!"=="3" goto push
if "!CMD!"=="4" goto auto_on
if "!CMD!"=="5" goto auto_off
if "!CMD!"=="6" goto status
if "!CMD!"=="0" exit /b 0
echo Invalid choice, please try again.
pause
goto menu

:gen
echo.
echo [1/6] Generating today's news ... live progress below
"%PYEXE%" %PYOPTS% app\control.py today
echo.
pause
goto menu

:open
for /f "delims=" %%d in ('"%PYEXE%" %PYOPTS% app\open_review.py') do set "RD=%%d"
if defined RD (explorer "!RD!") else (explorer review)
pause
goto menu

:push
echo.
echo [3/6] Select the review file; a local Chrome window will save it to WeChat drafts ...
"%PYEXE%" %PYOPTS% app\control.py push
echo.
pause
goto menu

:auto_on
"%PYEXE%" %PYOPTS% app\control.py auto on --time 09:00
echo Auto generation enabled at 09:00.
echo Starting scheduler now ... keep this window open (close it to stop).
"%PYEXE%" %PYOPTS% app\control.py serve
pause
goto menu

:auto_off
"%PYEXE%" %PYOPTS% app\control.py auto off
pause
goto menu

:status
"%PYEXE%" %PYOPTS% app\control.py status
pause
goto menu
