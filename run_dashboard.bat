@echo off
title SYNOPTYK-ARCTIC -- Dashboard (appka lokalna)
color 0B
cls

cd /d "%~dp0"

echo ============================================================
echo   SYNOPTYK-ARCTIC: Dashboard (FastAPI, dane na zywo z CSV)
echo   Katalog roboczy: %cd%
echo ============================================================
echo.

if exist "venv\Scripts\activate.bat" (
    echo [OK] Aktywacja venv...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo [OK] Aktywacja .venv...
    call .venv\Scripts\activate.bat
) else (
    echo [INFO] Uzywanie systemowej instalacji Pythona.
)

echo.
echo [1/2] Instalacja pakietow pip...
python -m pip install --upgrade pip --disable-pip-version-check
python -m pip install -r requirements.txt

if %ERRORLEVEL% NEQ 0 (
    echo [BLAD] Instalacja pakietow nie powiodla sie.
    pause
    exit /b 1
)

echo.
echo [2/2] Uruchamianie dashboardu na http://127.0.0.1:8000 ...
echo.
echo (Kazde odswiezenie strony w przegladarce na nowo czyta aktualny
echo  arctic_forecast_snapshots.csv - nie trzeba nic regenerowac.
echo  Zamknij to okno (Ctrl+C), zeby zatrzymac serwer.)
echo.

start "" http://127.0.0.1:8000
python -m uvicorn webapp.app:app --host 127.0.0.1 --port 8000

pause
