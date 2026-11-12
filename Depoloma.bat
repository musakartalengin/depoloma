@echo off
rem Depoloma launcher for Windows - double-click to start.
rem Finds Python, then opens the Depoloma window (no console stays open).
setlocal EnableExtensions
cd /d "%~dp0"

set "PY="
set "PYW="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
if not errorlevel 1 (
    set "PY=py -3"
    where pyw >nul 2>nul && set "PYW=pyw -3"
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PY=python"
        where pythonw >nul 2>nul && set "PYW=pythonw"
    )
)
if not defined PY goto :nopython

if "%~1"=="" (
    if defined PYW (
        start "" %PYW% -m depoloma
    ) else (
        start "Depoloma" /min %PY% -m depoloma
    )
    exit /b 0
)
rem With arguments (e.g. --report) run in this console so the output is visible.
%PY% -m depoloma %*
exit /b %errorlevel%

:nopython
echo.
echo   Depoloma icin Python 3.8 veya ustu gerekiyor ^(Depoloma needs Python 3.8+^).
echo.
where winget >nul 2>nul
if errorlevel 1 (
    echo   Python'u https://www.python.org/downloads/ adresinden kurup tekrar deneyin.
    echo   Install Python from https://www.python.org/downloads/ and try again.
    echo.
    pause
    exit /b 1
)
choice /C EH /N /M "  Python simdi winget ile kurulsun mu? Install Python now with winget? [E=Evet/Yes, H=Hayir/No] "
if errorlevel 2 exit /b 1
winget install -e --id Python.Python.3.12 --scope user
echo.
echo   Kurulum bitti. Depoloma.bat dosyasini yeniden calistirin.
echo   Done. Run Depoloma.bat again.
echo.
pause
exit /b 0
