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
    app.py              — FastAPI: /api/status, /api/real_bias, /api/demo_bias, /api/latest_readings, /
    static/index.html   — dashboard (JS + Chart.js z CDN, czyta API na żywo)
run_dashboard.bat       — uruchamia dashboard www
arctic_forecast_snapshots.csv         — realne dane z bieżących uruchomień
demo_synthetic_arctic_snapshots.csv   — syntetyczne dane demo, osobno od realnych
backtest_real.py        — realny backtest historyczny (Previous Runs API), uruchamiać lokalnie
tests/                  — 45 testów, w tym na fixtures z prawdziwego API
```

## Instalacja i uruchomienie

```bash
pip install -r requirements.txt
pytest -v                   # 45 testów
python run_arctic.py        # codzienne pobranie + log (uruchamiać lokalnie)
```

## Status testów

45/45 testów przechodzi — w tym 4 bezpośrednio na prawdziwych odpowiedziach
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
- **Surowe odczyty** — osobna tabela nad tabelą trafności, pokazująca
  ostatnie surowe wiersze z `arctic_forecast_snapshots.csv` (i "prognoza",
  i "archiwum_openmeteo") bez żadnego progu/parowania. Dodane po pytaniu
  użytkownika, czy da się w ogóle zobaczyć, że kolektor działa, zanim
  uzbiera się `min_samples=5` par do tabeli trafności — bo `/api/real_bias`
  celowo pokazuje pustą tabelę na starcie (patrz wyżej), co bez tego widoku
  wygląda identycznie jak "nic się nie zbiera", nawet gdy zbiera.

### Endpointy

| endpoint | zwraca |
|---|---|
| `GET /api/status` | metadane stacji + liczba dni + poziom świeżości |
| `GET /api/real_bias` | oficjalny bias/MAE (>=5 par) + surowe liczniki n |
| `GET /api/demo_bias` | bias/MAE na danych syntetycznych + disclaimer |
| `GET /api/latest_readings` | ostatnie N surowych, niesparowanych wierszy z REAL_CSV — widoczność że kolektor pisze dane, niezależnie od progu `min_samples` |

### Testy

`tests/test_webapp.py` (10 testów) — na izolowanych, tymczasowych CSV
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

## Etap 4 — backtest historyczny (realny i symulowany)

`run_arctic.py` zbiera dane na bieżąco (tygodnie do pierwszego wyniku).
Dwa dodatkowe narzędzia dają wgląd w trafność szybciej — jedno na
prawdziwej historii, drugie na w pełni zmyślonych danych. Oba są jawnie
opisane co do statusu, żeby nie dało się ich pomylić.

### `backtest_real.py` — prawdziwa historia z Open-Meteo, natychmiastowa

Open-Meteo ma **Previous Runs API**
(`previous-runs-api.open-meteo.com`) — archiwum prognoz sprzed lat na
stałych lead_days (1–7 dni), zaprojektowane właśnie do oceny skuteczności
prognoz w czasie. `arctic_synoptyk/previous_runs.py` pobiera to i paruje
z `fetch_archive()` (rzeczywistość) — daje realny bias/MAE per lead_days
z wielu miesięcy historii jednym zapytaniem, zamiast czekać tygodniami.

```bash
python backtest_real.py 90    # 90 dni prawdziwej historii Longyearbyen
```

**Status: zweryfikowane na prawdziwej odpowiedzi API 2026-08-27** — parser
zadziałał bez poprawek, zgodnie z udokumentowanym kształtem odpowiedzi.
Wynik pierwszego uruchomienia (90 dni, Longyearbyen, Best Match — patrz
zastrzeżenie niżej):

| lead_days | n | bias °C | MAE °C |
|---|---|---|---|
| 1 | 90 | +0.28 | 0.48 |
| 2 | 90 | +0.28 | 0.69 |
| 3 | 90 | +0.35 | 0.81 |
| 4 | 90 | +0.15 | 0.93 |
| 5 | 90 | +0.06 | 1.30 |
| 6 | 90 | -0.14 | 1.74 |
| 7 | 90 | -0.33 | 1.76 |

MAE rośnie z lead_days (0.48°C → 1.76°C) — zgodne z oczekiwanym spadkiem
trafności prognozy wraz z horyzontem, dobry sygnał, że metoda mierzy
prawdziwe zjawisko, nie artefakt. Bias zmienia znak między lead_days 5 i
6 (niedoszacowanie → przeszacowanie) — może być realny efekt modelu, może
zbieg okoliczności dla tego konkretnego okna/lokalizacji; **jedno
90-dniowe okno jednej stacji arktycznej, nie generalny wniosek o
Open-Meteo**. Liczby będą się zmieniać przy kolejnych uruchomieniach (inne
okno czasowe) — traktować jako punkt odniesienia, nie stałą.

Testy (`test_previous_runs.py`) nadal używają ręcznie zbudowanego
payloadu (zgodnego z dokumentacją, teraz też potwierdzonego realną
odpowiedzią) — nie zapisano surowej odpowiedzi API jako fixture, bo
`backtest_real.py` był uruchomiony poza tym środowiskiem.

### `demo_synthetic_fill.py` — symulacja, natychmiastowa, w pełni zmyślona

```bash
python demo_synthetic_fill.py 90    # 90 symulowanych dni zamiast domyślnych 21
```

Generuje w pełni sztuczne dane (`demo_synthetic_arctic_snapshots.csv`,
stacja `Longyearbyen_Svalbard_DEMO`) z zamierzonym wzorcem obciążenia
(`bias(lead) = 1.2 − 0.35·lead`) i pokazuje, że `compute_lead_bias()`
poprawnie go odtwarza przy większej próbce (n=90 zamiast n=21 zbliża
wynik do zamierzonych wartości). To demo MECHANIZMU, nie prognoza
niczego o Longyearbyen — każdy wiersz i wydruk jest tagowany `[DEMO]`.
