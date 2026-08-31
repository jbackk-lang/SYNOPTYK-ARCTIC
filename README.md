# SYNOPTYK-ARCTIC

Wersja Synoptyka dla stacji arktycznych/zdalnych — **10 stacji**
(przełącznik w dashboardzie, pogrupowany na Północ/Południe): 6 stacji
arktycznych (Longyearbyen, Ny-Ålesund i Polska Stacja Polarna Hornsund na
Svalbardzie, Alert w Kanadzie, Utqiagvik na Alasce, Tiksi w Rosji) +
**4 stacje antarktyczne** (Polska Stacja Antarktyczna im. Henryka
Arctowskiego, McMurdo, Amundsen-Scott na biegunie południowym, Wostok) —
patrz "Wiele stacji" niżej po szczegóły i uzasadnienie tego wyjątku od
nazwy projektu. Domyślna stacja: **Hornsund** (Polska Stacja Polarna).
Wszystkie współrzędne w `arctic_synoptyk/station.py`. Cztery gotowe,
przetestowane elementy:

1. **Zbieranie danych + pomiar trafności** — codzienny kolektor
   (`run_arctic.py`) loguje prognozę i archiwum Open-Meteo do CSV, licząc
   po drodze bias/MAE per `lead_days`. CSV jest automatycznie przycinany do
   ostatnich 30 dni (patrz "Retencja CSV" niżej) — nic nie ginie, starsze
   wiersze trafiają do pliku archiwalnego.
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

## Szybki start

Bez tego kroku dashboard pokazuje "za mało danych" przez pierwsze ~2
tygodnie codziennego zbierania (`compute_lead_bias()` potrzebuje >= 5
sparowanych dni NA DANY `lead_days`, a codzienne zbieranie daje najwyżej
jedną taką parę dziennie — patrz `HISTORIA_BUDOWY.md`). Żeby zobaczyć
wynik od razu, zasil CSV prawdziwą historią jednym uruchomieniem:

```bash
python backfill_real_history.py    # jednorazowo: 30 dni prawdziwej historii
                                    # z Open-Meteo (Previous Runs + Archive API)
                                    # -> arctic_forecast_snapshots.csv
```

**Uruchamiać lokalnie** — dostęp do `api.open-meteo.com` jest zablokowany
w tutejszym środowisku deweloperskim (sandbox). Potem zwyczajnie:

```bash
python run_arctic.py        # codziennie, albo: run.bat
```

żeby CSV rósł dalej na bieżąco, obok tego, co dociągnął backfill (patrz
"Retencja CSV" niżej — obie ścieżki dzielą to samo okno 30 dni).
`backfill_real_history.py` jest bezpieczny do pominięcia — bez niego
wszystko działa tak samo, tylko trzeba poczekać na wynik.

## Codzienne zbieranie danych

```bash
python run_arctic.py        # albo: run.bat
```

Dopisuje wiersze do `arctic_forecast_snapshots.csv` (prognoza + archiwum)
i pokazuje aktualny stan korekty obciążenia. `compute_lead_bias()` zwraca
pusty wynik, dopóki nie zbierze się >= 5 sparowanych dni na dany
`lead_days` — to normalne na początku, nie błąd (albo użyj
`backfill_real_history.py` wyżej, żeby nie czekać). Uruchamiaj codziennie
(np. jako zadanie zaplanowane w Windows), żeby CSV realnie narósł.

### Retencja CSV

Po każdym dopisaniu (`run_arctic.py` i `backfill_real_history.py`)
`arctic_forecast_snapshots.csv` jest automatycznie przycinany do
ostatnich **30 dni** (licząc po `target_date`) — 30 dni z zapasem
wystarcza na policzenie bias/MAE nawet dla najdłuższego horyzontu (7 dni,
patrz `arctic_synoptyk/retention.py`). Nic nie jest kasowane bezpowrotnie:
starsze wiersze trafiają do `arctic_forecast_snapshots_archive.csv` (ten
sam układ kolumn, nigdy nie przycinany) — pełna historia zawsze dostępna
do ręcznej analizy, plik roboczy zostaje mały.

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
| `GET /api/stations` | lista wszystkich stacji (nazwa + współrzędne + półkula), plus już pogrupowane `north`/`south` do dropdowna |
| `GET /api/status` | metadane stacji + liczba dni + poziom świeżości |
| `GET /api/real_bias` | oficjalny bias/MAE (>=5 par) + surowe liczniki n |
| `GET /api/demo_bias` | bias/MAE na danych syntetycznych + disclaimer |
| `GET /api/latest_readings` | ostatnie N surowych, niesparowanych wierszy z CSV — widoczność że kolektor pisze dane, niezależnie od progu `min_samples` |
| `POST /api/collect` | uruchamia realne pobranie z Open-Meteo dla jednej stacji i dopisanie do CSV, zwraca to, co zebrało (albo `forecast_error`/`archive_error`, jeśli sieć zawiodła) |

`/api/status`, `/api/real_bias`, `/api/latest_readings`, `POST /api/collect`
przyjmują opcjonalny `?station=<nazwa>` (patrz "Wiele stacji" niżej) —
brak parametru = domyślnie Longyearbyen, nieznana nazwa = HTTP 404
(jawny błąd, nie cichy fallback).

## Wiele stacji

Dashboard ma przełącznik (dropdown, dwie grupy: 🧭 Północ / 🧊 Południe)
między **10 stacjami**, wszystkie na **wspólnym**
`arctic_forecast_snapshots.csv` (rozróżnione kolumną `station` —
`snapshots.py`/`bias.py` filtrowały po niej od początku, więc dodanie
kolejnych stacji nie wymagało zmiany schematu). Domyślna: **Hornsund**
(`DEFAULT_STATION` w `webapp/app.py`).

### Północ (Arktyka)

| stacja (nazwa w CSV) | lokalizacja | uwaga |
|---|---|---|
| `Hornsund_Polska_Stacja_Polarna` | Svalbard, Norwegia | **domyślna** — Polska Stacja Polarna (IGF PAN) |
| `Longyearbyen_Svalbard` | Svalbard, Norwegia | jedyna zweryfikowana na żywym fetchu (patrz "Znane ograniczenia") |
| `Ny_Alesund_Svalbard` | Svalbard, Norwegia | najdalej na północ wysunięta stała osada badawcza świata |
| `Alert_Nunavut_Kanada` | Wyspa Ellesmere'a, Kanada | najdalej na północ wysunięta stale zamieszkana osada świata (82°N) |
| `Utqiagvik_Alaska` | Alaska, USA | stacja klimatyczna NOAA |
| `Tiksi_Rosja` | Jakucja, Rosja | Morze Łaptiewów |

### Południe (Antarktyda) ⚠️

| stacja (nazwa w CSV) | lokalizacja | uwaga |
|---|---|---|
| `Arctowski_Antarktyda` | Wyspa Króla Jerzego | Polska Stacja Antarktyczna im. Henryka Arctowskiego |
| `McMurdo_Antarktyda` | Wyspa Rossa | największa stacja badawcza na Antarktydzie (USAP) |
| `Amundsen_Scott_Biegun_Poludniowy` | biegun południowy (90°S) | długość geograficzna umownie 0°E — nieokreślona matematycznie w tym punkcie |
| `Wostok_Antarktyda` | wnętrze Antarktydy Wschodniej | najniższa zarejestrowana temperatura na Ziemi (-89.2°C, 1983) |

**`python run_arctic.py`** i **`python backfill_real_history.py`** zbierają
teraz WSZYSTKIE 10 stacji jednym uruchomieniem (`run_arctic.collect_all()`/
pętla w `backfill_real_history.main()`) — nie trzeba mnożyć zaplanowanych
zadań per stacja. Błąd sieci dla jednej stacji nie przerywa reszty.
`POST /api/collect` w dashboardzie działa na jednej, aktualnie wybranej w
dropdownie stacji (szybciej niż czekać na 10 zapytań do Open-Meteo na
jedno kliknięcie).

**4 stacje antarktyczne, nie Arktyka** — świadomy wyjątek od nazwy
projektu, dodany na wyraźną prośbę użytkownika (Arctowski jako druga,
obok Hornsund, polska całoroczna stacja polarna; potem dołożone McMurdo/
Amundsen-Scott/Wostok po pytaniu "czy są inne stacje oprócz
arctowskiego"). Sezony są tam odwrócone (antarktyczne lato =
grudzień-luty) — "noc polarna listopad-luty" niżej w "Znanych
ograniczeniach" dotyczy WYŁĄCZNIE stacji na półkuli północnej. Dashboard
pokazuje jawne ostrzeżenie pod nagłówkiem, gdy jakakolwiek stacja
południowa jest wybrana (liczone z `ArcticStation.hemisphere`, nie z
dopasowania nazwy — dotyczy więc też Amundsen-Scott, mimo że w jej
nazwie nie ma słowa "Antarktyda").

## Backtest historyczny (bez zapisu do CSV)

`backfill_real_history.py` (patrz "Szybki start" wyżej) jest tym, czego
zwykle chcesz — dopisuje realną historię do `arctic_forecast_snapshots.csv`,
więc dashboard widzi wynik od razu. Dwa dodatkowe warianty, gdy chcesz
tylko PODEJRZEĆ liczby bez dotykania CSV:

```bash
python backtest_real.py 90        # prawdziwa historia (Previous Runs API), tylko na konsolę
python demo_synthetic_fill.py 90  # w pełni syntetyczne dane, demo mechanizmu compute_lead_bias()
```

`backfill_real_history.py` dopisuje prawdziwe, historyczne pary
prognoza/rzeczywistość pod tymi samymi etykietami `source` co codzienne
zbieranie (`prognoza`/`archiwum_openmeteo`) — świadomy kompromis,
uzasadnienie w `HISTORIA_BUDOWY.md`. Idempotentne (bezpiecznie uruchomić
kilka razy albo obok `run_arctic.py`). Domyślnie pobiera i zatrzymuje 30
dni historii (`python backfill_real_history.py [dni_historii] [retencja_dni]`
— podaj oba razem, jeśli świadomie chcesz dłuższe okno niż domyślna
retencja).

## Testy

```bash
pytest -v
```

Wszystkie testy przechodzą (stan na 2026-08-31: 88/88) — w tym część
bezpośrednio na prawdziwych odpowiedziach API z 2026-08-26
(`test_fetch.py`), na izolowanych/tymczasowych CSV (`test_webapp.py`,
monkeypatch `webapp.app.REAL_CSV`/`DEMO_CSV`, nigdy nie dotyka prawdziwych
plików w repo).

## Struktura repo

```
arctic_synoptyk/
    station.py          — ArcticStation (bez UHI, bez cichego fallbacku) + STATIONS/STATIONS_BY_NAME/STATIONS_NORTH/STATIONS_SOUTH (10 stacji, patrz "Wiele stacji")
    fetch.py             — pobieranie z Open-Meteo (daily=), parsowanie odpowiedzi
    snapshots.py         — logowanie do CSV (idempotentne)
    bias.py              — bias/MAE per lead_days
    previous_runs.py     — Previous Runs API (backtest historyczny)
    retention.py          — przycina CSV do ostatnich 30 dni, stare wiersze do archiwum (nic nie kasuje)
    offline.py           — lokalny bufor, wskaźnik nieaktualności, degradowana estymacja
    connectivity_sim.py  — symulacja wielodniowej przerwy w łączności
run_arctic.py            — codzienny runner (collect() + CLI; uruchamiać lokalnie, nie w sandboksie)
fetch_arctic_test.py     — samodzielny skrypt testowy (bez zależności)
backfill_real_history.py — jednorazowe zasilenie CSV realną historią (patrz "Szybki start"), uruchamiać lokalnie
backtest_real.py         — jak wyżej, ale tylko na konsolę, nic nie zapisuje, uruchamiać lokalnie
demo_synthetic_fill.py   — generuje syntetyczne dane demo (osobny CSV/stacja)
webapp/
    app.py               — FastAPI: status/real_bias/demo_bias/latest_readings/collect (patrz tabela wyżej)
    static/index.html    — dashboard (JS + Chart.js zwendorowany lokalnie, czyta API na żywo)
    static/vendor/        — Chart.js lokalnie (v4.4.4, MIT) — dashboard działa offline
run_dashboard.bat        — uruchamia dashboard www
arctic_forecast_snapshots.csv         — realne dane, ostatnie 30 dni (patrz "Retencja CSV")
arctic_forecast_snapshots_archive.csv — starsze realne dane, nigdy nie przycinany, tworzony automatycznie
demo_synthetic_arctic_snapshots.csv   — syntetyczne dane demo, osobno od realnych
tests/                   — 74 testy, w tym na fixtures z prawdziwego API
HISTORIA_BUDOWY.md       — pełna historia decyzji i naprawionych błędów
```

## Znane ograniczenia

- Sandbox deweloperski nie ma dostępu do `api.open-meteo.com` —
  `run_arctic.py`, `backtest_real.py`, `backfill_real_history.py` i
  dashboard z realnym `/api/collect` trzeba uruchamiać lokalnie.
- `temp_avg_c_approx` w CSV to (max+min)/2, **nie** prawdziwa średnia
  dobowa (Open-Meteo agreguje dobowo po swojej stronie, bez godzinowego
  sygnału) — traktować jako przybliżenie.
- Zachowanie w okresie nocy polarnej (listopad–luty) nie sprawdzone —
  dotychczasowe dane pokrywają tylko letnie okno. Dotyczy WYŁĄCZNIE
  stacji na półkuli północnej (6 z 7) — dla `Arctowski_Antarktyda` pory
  roku są odwrócone (antarktyczne lato = grudzień-luty), patrz "Wiele
  stacji" wyżej.
- Współrzędne/wysokości nowych stacji (wszystkie poza Longyearbyen) NIE
  są jeszcze zweryfikowane na żywym zapytaniu do Open-Meteo (`grid_lat`/
  `grid_lon`/`grid_elevation_m` w `station.py` puste) — tylko z publicznych
  źródeł (Wikipedia/NOAA/strony instytucji). Pierwszy realny fetch dla
  każdej z nich to zweryfikuje (patrz komentarz przy LONGYEARBYEN, ten sam
  wzorzec przyciągania do punktu siatki).
- Brak integracji z fizycznym sprzętem satelitarnym (Iridium/Argos) —
  `connectivity_sim.py` tylko symuluje harmonogram połączeń.
- `arctic_forecast_snapshots.csv` pokazuje tylko ostatnie 30 dni
  (retencja, patrz wyżej) — pełna historia jest w
  `arctic_forecast_snapshots_archive.csv`, ale `compute_lead_bias()`/
  dashboard go nie czytają, tylko plik "gorący".
- `wind_direction_deg` (kierunek wiatru) jest ZAWSZE pusty w wierszach
  "prognoza" dopisanych przez `backfill_real_history.py` — to wielkość
  kołowa (średnia z 350° i 10° to fizycznie 0°, nie 180°), a Previous Runs
  API dostarcza tylko surowy sygnał godzinowy, więc świadomie nie
  próbujemy go tu agregować samodzielnie. Wypełniony jest normalnie dla
  wierszy z `run_arctic.py` i archiwum — tam Open-Meteo sam liczy
  dominujący kierunek dobowy poprawną metodą, po swojej stronie.
- Wiersze zapisane PRZED dodaniem `wind_direction_deg` do `fetch.py`
  (2026-08-31) mają to pole trwale puste w dashboardzie, dopóki nie
  klikniesz jeszcze raz "▶ Pobierz nowe dane teraz" (albo nie odpali się
  `run_arctic.py`) — `append_snapshot()` przy tym samym kluczu
  uzupełnia brakujące pole w miejscu, zamiast czekać na jutrzejszy
  `issue_date` (patrz `HISTORIA_BUDOWY.md`).

Szczegóły i uzasadnienia każdego z powyższych: [`HISTORIA_BUDOWY.md`](HISTORIA_BUDOWY.md).
