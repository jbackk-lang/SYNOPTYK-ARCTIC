# SYNOPTYK-ARCTIC

Wersja Synoptyka dla stacji arktycznej/zdalnej (Longyearbyen, Svalbard —
lat 78.2232, lon 15.6267). Cztery gotowe, przetestowane elementy:

1. **Zbieranie danych + pomiar trafności** — codzienny kolektor
   (`run_arctic.py`) loguje prognozę i archiwum Open-Meteo do CSV, licząc
   po drodze bias/MAE per `lead_days`.
2. **Odporność na przerwy w łączności** — lokalny bufor odczytów +
   wskaźnik nieaktualności danych, myślący w kategoriach dni/tygodni
   przerwy satelitarnej, nie chwilowego zerwania Wi-Fi.
3. **Dashboard www** — lokalna appka FastAPI, czyta CSV na żywo przy
   każdym żądaniu.
4. **Backtest historyczny** — natychmiastowy wgląd w trafność (prawdziwa
   historia z Open-Meteo Previous Runs API + wariant w pełni syntetyczny),
   bez czekania tygodniami na `run_arctic.py`.

Pełna historia decyzji, znalezionych i naprawionych błędów oraz wyniki
backtestu są w [`HISTORIA_BUDOWY.md`](HISTORIA_BUDOWY.md) — ten plik
zawiera tylko to, co potrzebne do instalacji i uruchomienia.

## Instalacja

```bash
pip install -r requirements.txt
```

## Codzienne zbieranie danych

```bash
python run_arctic.py        # albo: run.bat
```

Dopisuje wiersze do `arctic_forecast_snapshots.csv` (prognoza + archiwum)
i pokazuje aktualny stan korekty obciążenia. **Uruchamiać lokalnie** —
dostęp do `api.open-meteo.com` jest zablokowany w tutejszym środowisku
deweloperskim (sandbox). `compute_lead_bias()` zwraca pusty wynik, dopóki
nie zbierze się >= 5 sparowanych dni na dany `lead_days` — to normalne na
początku, nie błąd. Uruchamiaj codziennie (np. jako zadanie zaplanowane
w Windows), żeby CSV realnie narósł.

## Dashboard www

```bash
run_dashboard.bat
```

albo ręcznie:

```bash
pip install -r requirements.txt
python -m uvicorn webapp.app:app --host 127.0.0.1 --port 8000
# otwórz http://127.0.0.1:8000
```

Każde odświeżenie strony na nowo czyta aktualny `arctic_forecast_snapshots.csv`
z dysku — nie trzeba nic regenerować. Przycisk "▶ Pobierz nowe dane teraz"
w dashboardzie robi to samo, co `python run_arctic.py`, jednym kliknięciem
(patrz `POST /api/collect` niżej); "↻ Odśwież teraz" tylko na nowo czyta
to, co już jest na dysku.

### Endpointy

| endpoint | zwraca |
|---|---|
| `GET /api/status` | metadane stacji + liczba dni + poziom świeżości |
| `GET /api/real_bias` | oficjalny bias/MAE (>=5 par) + surowe liczniki n |
| `GET /api/demo_bias` | bias/MAE na danych syntetycznych + disclaimer |
| `GET /api/latest_readings` | ostatnie N surowych, niesparowanych wierszy z CSV — widoczność że kolektor pisze dane, niezależnie od progu `min_samples` |
| `POST /api/collect` | uruchamia realne pobranie z Open-Meteo i dopisanie do CSV, zwraca to, co zebrało (albo `forecast_error`/`archive_error`, jeśli sieć zawiodła) |

## Backtest historyczny (wynik bez czekania tygodniami)

```bash
python backtest_real.py 90          # prawdziwa historia (Previous Runs API), 90 dni
python demo_synthetic_fill.py 90    # w pełni syntetyczne dane, demo mechanizmu
```

## Testy

```bash
pytest -v
```

Wszystkie testy przechodzą (stan na 2026-08-30: 52/52) — w tym część
bezpośrednio na prawdziwych odpowiedziach API z 2026-08-26
(`test_fetch.py`), na izolowanych/tymczasowych CSV (`test_webapp.py`,
monkeypatch `webapp.app.REAL_CSV`/`DEMO_CSV`, nigdy nie dotyka prawdziwych
plików w repo).

## Struktura repo

```
arctic_synoptyk/
    station.py          — ArcticStation (bez UHI, bez cichego fallbacku)
    fetch.py             — pobieranie z Open-Meteo (daily=), parsowanie odpowiedzi
    snapshots.py         — logowanie do CSV (idempotentne)
    bias.py              — bias/MAE per lead_days
    previous_runs.py     — Previous Runs API (backtest historyczny)
    offline.py           — lokalny bufor, wskaźnik nieaktualności, degradowana estymacja
    connectivity_sim.py  — symulacja wielodniowej przerwy w łączności
run_arctic.py            — codzienny runner (collect() + CLI; uruchamiać lokalnie, nie w sandboksie)
fetch_arctic_test.py     — samodzielny skrypt testowy (bez zależności)
backtest_real.py         — realny backtest historyczny (Previous Runs API), uruchamiać lokalnie
demo_synthetic_fill.py   — generuje syntetyczne dane demo (osobny CSV/stacja)
webapp/
    app.py               — FastAPI: status/real_bias/demo_bias/latest_readings/collect (patrz tabela wyżej)
    static/index.html    — dashboard (JS + Chart.js zwendorowany lokalnie, czyta API na żywo)
    static/vendor/        — Chart.js lokalnie (v4.4.4, MIT) — dashboard działa offline
run_dashboard.bat        — uruchamia dashboard www
arctic_forecast_snapshots.csv         — realne dane z bieżących uruchomień
demo_synthetic_arctic_snapshots.csv   — syntetyczne dane demo, osobno od realnych
tests/                   — 52 testy, w tym na fixtures z prawdziwego API
HISTORIA_BUDOWY.md       — pełna historia decyzji i naprawionych błędów
```

## Znane ograniczenia

- Sandbox deweloperski nie ma dostępu do `api.open-meteo.com` —
  `run_arctic.py`, `backtest_real.py` i dashboard z realnym `/api/collect`
  trzeba uruchamiać lokalnie.
- `temp_avg_c_approx` w CSV to (max+min)/2, **nie** prawdziwa średnia
  dobowa (Open-Meteo agreguje dobowo po swojej stronie, bez godzinowego
  sygnału) — traktować jako przybliżenie.
- Zachowanie w okresie nocy polarnej (listopad–luty) nie sprawdzone —
  dotychczasowe dane pokrywają tylko letnie okno.
- Brak integracji z fizycznym sprzętem satelitarnym (Iridium/Argos) —
  `connectivity_sim.py` tylko symuluje harmonogram połączeń.

Szczegóły i uzasadnienia każdego z powyższych: [`HISTORIA_BUDOWY.md`](HISTORIA_BUDOWY.md).
