@echo off
REM 토스증권 실데이터로 삼성전자(+피어) 분석 리포트를 생성하고 브라우저로 엽니다.
REM 더블클릭하거나, 명령창에서: run.bat  또는  run.bat --demo
setlocal
cd /d "%~dp0"

where python >nul 2>nul && (set PY=python) || (set PY=python3)
%PY% --version >nul 2>nul || (echo [X] Python 3.9+ 가 필요합니다. https://python.org && pause && exit /b 1)

REM --demo 는 자격증명 없이 통과
echo %* | find "--demo" >nul
if errorlevel 1 (
  if "%TOSSINVEST_CLIENT_ID%"=="" set /p TOSSINVEST_CLIENT_ID=Client Id (tsck_live_...):
  if "%TOSSINVEST_CLIENT_SECRET%"=="" set /p TOSSINVEST_CLIENT_SECRET=Client Secret (tssk_live_...):
)

if "%~1"=="" (
  %PY% main.py --domestic A005930 --overseas NVDA --out out\samsung.html
  set OUT=out\samsung.html
) else (
  %PY% main.py %*
  set OUT=out\report.html
)

if exist "%OUT%" (
  echo Report: %OUT%
  start "" "%OUT%"
)
pause
