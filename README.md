# SYNOPTYK-ARCTIC

Wersja Synoptyka dla stacji arktycznej/zdalnej. Powstaje w dwóch etapach:

1. **Realna stacja arktyczna + pomiar trafności** (gotowe).
2. **Architektura odporna na przerwy w łączności** (offline-resilient) — w budowie.

## Etap 1 — stan i dane

### Stacja: Longyearbyen, Svalbard

Wybrana jako znana, realna lokalizacja arktyczna z publicznie dostępnymi
danymi Open-Meteo. Automatyczny dostęp do `api.open-meteo.com` z tego
środowiska deweloperskiego jest zablokowany (proxy sandbox, 403
blocked-by-allowlist) — pierwsze pobranie i test połączenia wykonano
lokalnie 2026-08-26. Pliki `tests/fixtures/arctic_*_result.json` to
niezmienione odpowiedzi API, nie mocki.

Wynik tego testu (`arctic_synoptyk/station.py::LONGYEARBYEN`):

| | żądane | zwrócone przez Open-Meteo |
|---|---|---|
| szerokość | 78.2232 | 78.20738 |
| długość | 15.6267 | 15.697675 |
| wysokość | — | 26.0 m |

Rozjazd (~1.6 km) to normalne przyciągnięcie do najbliższego punktu siatki
modelu globalnego (ECMWF/ICON), nie błąd.

### Różnice metodologiczne vs Synoptyk-v2.0 (Kraków)

- **Brak korekty UHI.** "Miejska wyspa ciepła" nie ma zastosowania do
  zdalnej lokalizacji arktycznej — `ArcticStation` nie ma pola `uhi`.
  Test: `test_station.py::test_longyearbyen_no_uhi_field`.
- **Brak cichego fallbacku dla nieznanej stacji.** `topomap_data.py` w
  Synoptyk-v2.0 dla nieznanej nazwy zwraca `lat=52.0, lon=19.0` (środek
  Polski). Tu nie ma mechanizmu "nazwa → współrzędne z fallbackiem": każda
  stacja to jawnie skonstruowany `ArcticStation`. Test:
  `test_station.py::test_no_silent_default_for_missing_station`.
- **Dobowy endpoint (`daily=`), nie godzinowy (`hourly=`).** Kraków pobiera
  godzinowe dane i agreguje do dobowych (średnia z 24 punktów). Tu
  Open-Meteo agreguje dobowo po swojej stronie — `temp_avg_c_approx` to
  (max+min)/2, nie prawdziwa średnia dobowa, i będzie się systematycznie
  różnić od niej dla asymetrycznych przebiegów temperatury. Traktować jako
  przybliżenie, nie tę samą wielkość co `avg_temp_c` w Krakowie.
- **Źródło "rzeczywistości" to `archiwum_openmeteo`**, ten sam status co
  `OpenMeteo_real_dailymax` w Synoptyk-v2.0 (reanaliza/najlepsze dostępne
  dane, nie surowy odczyt z fizycznego czujnika — żaden nie jest tu
  podłączony).

### Co wiadomo, a czego jeszcze nie

**Wiadomo:** pobieranie działa, zwraca kompletne dane dla sierpnia 2026 —
7 dni prognozy + 11 dni archiwum, wszystkie pola obecne
(`test_fetch.py::test_no_missing_values_in_august_fixtures`).

**Nie wiadomo jeszcze:** jaka jest faktyczna trafność prognozy dla tej
stacji. `compute_lead_bias()` celowo zwraca pusty słownik, dopóki nie
zbierze się >= 5 sparowanych dni per `lead_days` — dokładnie ten sam
mechanizm co dla Krakowa (1236 par po kilku tygodniach regularnego
uruchamiania). Żeby dostać wynik dla Svalbardu, trzeba uruchamiać
`run_arctic.py` codziennie przez kilka tygodni.

**Nie sprawdzone:** zachowanie w okresie nocy polarnej (listopad–luty) —
obecne dane pokrywają tylko letnie okno.

### Historia poprawek: dwa bugi znalezione na realnym użyciu (2026-08-27)

Pierwsze wielokrotne uruchomienie `run_arctic.py` tego samego dnia dało
`lead_days=0: bias=+0.00 MAE=0.00 n=5` — wygląda podejrzanie idealnie, i
faktycznie było błędem, nie dobrym wynikiem:

1. **Duplikacja wierszy.** `append_snapshot()` nie sprawdzało, czy dany
   wiersz (`station`, `target_date`, `issue_date`, `source`) już istnieje
   w CSV — każde uruchomienie skryptu tego samego dnia dopisywało te same
   dane ponownie. `n=5` to był w rzeczywistości **jeden** dzień
   zduplikowany 5×, nie 5 niezależnych dni. Naprawione: `append_snapshot()`
   jest teraz idempotentne po tym kluczu (test:
   `test_snapshots.py::test_append_same_day_twice_is_idempotent`).
2. **Archiwum Open-Meteo dla ostatnich ~2 dni nie jest sfinalizowaną
   reanalizą** — zwraca praktycznie tę samą liczbę co model prognozy,
   bo prawdziwa obserwacja/reanaliza dla tak świeżej daty jeszcze nie
   jest gotowa (ten sam efekt opisany dla Krakowa: "Open-Meteo Archive
   API ma opóźnienie ~1–2 dni"). Efekt: prognoza i "rzeczywistość" dla
   `lead_days=0` porównywały się same ze sobą, stąd idealne 0.00.
   Naprawione: `fetch_archive()` ma teraz `exclude_trailing_days=2`
   (domyślnie), odcinający najświeższe dni przed zwróceniem wyniku (test:
   `test_fetch.py::test_fetch_archive_excludes_trailing_unreliable_days`).

Istniejący `arctic_forecast_snapshots.csv` wyczyszczono (usunięto
duplikaty i wiersze archiwalne z niesfinalizowanego okna) — po tej
korekcie CSV ma znowu 0 sparowanych dni (`compute_lead_bias()` zwraca
puste), co jest teraz **poprawnym**, uczciwym stanem, a nie regresem:
pierwsze prawdziwe pary (prognoza vs. archiwum sprzed ≥2 dni dla tej
samej daty) pojawią się po kolejnych ~2 dniach regularnego uruchamiania.

## Struktura repo

```
arctic_synoptyk/
    station.py          — ArcticStation (bez UHI, bez cichego fallbacku)
    fetch.py            — pobieranie z Open-Meteo (daily=), parsowanie odpowiedzi
    snapshots.py        — logowanie do CSV
    bias.py             — bias/MAE per lead_days
    offline.py          — Etap 2: lokalny bufor, wskaźnik nieaktualności, degradowana estymacja
    connectivity_sim.py — Etap 2: symulacja wielodniowej przerwy w łączności
run_arctic.py           — codzienny runner (uruchamiać lokalnie, nie w sandboksie)
fetch_arctic_test.py    — samodzielny skrypt testowy (bez zależności)
demo_synthetic_fill.py  — generuje syntetyczne dane demo (osobny CSV/stacja)
webapp/
    app.py              — FastAPI: /api/status, /api/real_bias, /api/demo_bias, /
    static/index.html   — dashboard (JS + Chart.js z CDN, czyta API na żywo)
run_dashboard.bat       — uruchamia dashboard www
arctic_forecast_snapshots.csv         — realne dane z bieżących uruchomień
demo_synthetic_arctic_snapshots.csv   — syntetyczne dane demo, osobno od realnych
tests/                  — 39 testów, w tym na fixtures z prawdziwego API
```

## Instalacja i uruchomienie

```bash
pip install -r requirements.txt
pytest -v                   # 39 testów
python run_arctic.py        # codzienne pobranie + log (uruchamiać lokalnie)
```

## Status testów

39/39 testów przechodzi — w tym 4 bezpośrednio na prawdziwych odpowiedziach
API z 2026-08-26 (`test_fetch.py`).

## Etap 3 — dashboard www (lokalna appka)

Dashboard to appka **FastAPI**, nie statyczny plik `.html` — każde żądanie
na nowo czyta aktualny stan CSV z dysku, więc odświeżenie przeglądarki
wystarczy, bez kroku regeneracji.

### Uruchomienie

```bash
run_dashboard.bat
```

albo ręcznie:

```bash
pip install -r requirements.txt
python -m uvicorn webapp.app:app --host 127.0.0.1 --port 8000
# otwórz http://127.0.0.1:8000
```

### Co pokazuje

- **Status stacji** — liczba wierszy/dni zebranych w
  `arctic_forecast_snapshots.csv`, data ostatniego pobrania, poziom
  nieaktualności (`classify_staleness()` z `offline.py`, liczony na
  rzeczywistej dacie ostatniego wiersza).
- **Trafność prognozy — dane realne** — `compute_lead_bias()` na
  `arctic_forecast_snapshots.csv`. Przy niewystarczającej liczbie dni
  wynik jest pusty (`official: {}`), plus tabela surowych liczników `n`
  per `lead_days` pokazująca postęp w kierunku progu `min_samples=5`.
- **Demo — dane syntetyczne** — ten sam mechanizm na
  `demo_synthetic_arctic_snapshots.csv` (`demo_synthetic_fill.py`),
  wizualnie odseparowany banerem ostrzegawczym i disclaimerem w każdej
  odpowiedzi `/api/demo_bias`.

### Endpointy

| endpoint | zwraca |
|---|---|
| `GET /api/status` | metadane stacji + liczba dni + poziom świeżości |
| `GET /api/real_bias` | oficjalny bias/MAE (>=5 par) + surowe liczniki n |
| `GET /api/demo_bias` | bias/MAE na danych syntetycznych + disclaimer |

### Testy

`tests/test_webapp.py` (7 testów) — na izolowanych, tymczasowych CSV
(monkeypatch `webapp.app.REAL_CSV`/`DEMO_CSV`), nie na plikach repo.

## Etap 2 — architektura odporna na przerwy w łączności

### Kluczowe rozróżnienie: przyrząd ≠ łączność

Automatyczna stacja arktyczna zwykle ma własne zasilanie (solar+bateria) i
loguje odczyty lokalnie cały czas, niezależnie od tego, czy działa łącze
satelitarne (Iridium/Argos), które bywa niedostępne przez dni czy tygodnie.
`_load_csv_history_fallback()` w Synoptyk-v2.0 nie ma tego rozróżnienia —
zakłada, że brak świeżego Open-Meteo oznacza brak czegokolwiek świeższego
niż ostatnie udane połączenie. Dla Arktyki to złe założenie.

### Co zbudowano

- **`LocalBuffer`** (`offline.py`) — trwały, append-only log odczytów
  (JSONL — przerwany zapis w połowie nie psuje całej historii). Przetrwa
  restart procesu (test: `test_local_buffer_persists_across_instances`).
- **`StalenessLevel`/`classify_staleness()`** — wskaźnik wieku danych z
  progami dopasowanymi do realnych przerw satelitarnych (🟢 <1 dzień,
  🟡 1–3 dni, 🟠 3–14 dni, 🔴 >14 dni) — szersze okno niż założenie
  "codziennego internetu" w oryginalnym CSV fallbacku Krakowa.
- **`degraded_forecast()`** — gdy nie ma świeżej prognozy z Open-Meteo,
  buduje estymację z lokalnego bufora metodą persystencji (ostatni znany
  odczyt), nie próbą odtworzenia filtru falkowego/SynoptykV4 na
  potencjalnie dziurawym sygnale. Wynik zawiera jawny poziom
  nieaktualności (`staleness`/`staleness_label_pl`).
- **`connectivity_sim.py`** — symulacja wielodniowej przerwy łączności
  (weryfikacja na prawdziwym sprzęcie satelitarnym nie jest tu możliwa).
  Zweryfikowano na symulowanej 20-dniowej przerwie
  (`test_connectivity_sim.py`): przyrząd loguje wszystkie 25 dni bez
  utraty danych, wskaźnik nieaktualności poprawnie eskaluje
  FRESH→AGING→STALE→CRITICAL i wraca do FRESH po przywróceniu łączności.

### Czego ten etap nie robi

- Brak integracji z fizycznym sprzętem satelitarnym (Iridium/Argos/inny)
  — `connectivity_sim.py` symuluje harmonogram połączeń, nie sterownik
  modemu.
- `degraded_forecast()` nie ekstrapoluje trendu — dane z tygodniowymi
  przerwami są zbyt zawodne dla trendu. Rozszerzenie o ekstrapolację (gdy
  bufor ma wystarczająco gęste dane) to możliwy przyszły krok.
- Brak mechanizmu wysyłki zaległych danych po odzyskaniu łączności —
  `unsynced_since()` zwraca listę do wysłania, ale nic jej jeszcze nie
  konsumuje.
