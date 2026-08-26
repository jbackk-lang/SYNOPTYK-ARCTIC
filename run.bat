@echo off
title SYNOPTYK-ARCTIC -- Longyearbyen, Svalbard
color 0B
cls

cd /d "%~dp0"

echo ============================================================
echo   SYNOPTYK-ARCTIC: pobranie + logowanie dobowe (Longyearbyen)
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

if not exist "run_arctic.py" (
    echo [BLAD] Nie znaleziono pliku run_arctic.py
    pause
    exit /b 1
)

echo.
echo [2/2] Pobieranie prognozy + archiwum, logowanie do CSV...
echo.
echo (Ten skrypt ma sens odpalany CODZIENNIE - kazde uruchomienie dopisuje
echo  nowy wiersz do arctic_forecast_snapshots.csv. compute_lead_bias()
echo  zostanie pusty, dopoki nie zbierze sie min. 5 sparowanych dni na
echo  dany lead_days - to normalne, patrz README.)
echo.

python run_arctic.py

echo.
echo ============================================================
echo Gotowe. Uruchom ponownie jutro (lub ustaw jako zadanie
echo zaplanowane w Harmonogramie zadan Windows), zeby CSV realnie
echo naros3 do punktu, w ktorym korekta obciazenia zacznie dzialac.
echo ============================================================
pause
