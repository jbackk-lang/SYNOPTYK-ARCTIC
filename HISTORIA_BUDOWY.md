# SYNOPTYK-ARCTIC — historia budowy i ustalenia

Pełna historia decyzji projektowych, znalezionych i naprawionych błędów oraz
wyników testów historycznych, w kolejności chronologicznej. Instrukcje
instalacji/uruchomienia i aktualna struktura repo są w `README.md` — tu
tylko "dlaczego" i "co się zmieniało po drodze".

## Etap 1 — realna stacja arktyczna + pomiar trafności (2026-08-26)

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

### Stan na 2026-08-26

**Wiadomo:** pobieranie działa, zwraca kompletne dane dla sierpnia 2026 —
7 dni prognozy + 11 dni archiwum, wszystkie pola obecne
(`test_fetch.py::test_no_missing_values_in_august_fixtures`).

**Nie wiadomo było jeszcze:** jaka jest faktyczna trafność prognozy dla tej
stacji — `compute_lead_bias()` celowo zwraca pusty słownik, dopóki nie
zbierze się >= 5 sparowanych dni per `lead_days`, dokładnie ten sam
mechanizm co dla Krakowa (1236 par po kilku tygodniach regularnego
uruchamiania).

**Nie sprawdzone (nadal aktualne):** zachowanie w okresie nocy polarnej
(listopad–luty) — dane pokrywają na razie tylko letnie okno.

### Dwa błędy znalezione na realnym użyciu (2026-08-27)

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
korekcie CSV miał znowu 0 sparowanych dni (`compute_lead_bias()` zwracał
puste), co było wtedy **poprawnym**, uczciwym stanem, a nie regresem.

## Etap 2 — architektura odporna na przerwy w łączności

Status: zrobione i przetestowane (nie "w budowie" — patrz zastrzeżenia w
"Czego ten etap nie robi" niżej co do zakresu).

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

## Etap 3 — dashboard www (lokalna appka)

### Poprawka: przycisk "Odśwież teraz" nic nie robił (2026-08-29)

Zgłoszenie: dane się zbierają poprawnie (`run.bat`/`run_arctic.py`
dopisuje do CSV bez problemu), ale przycisk odświeżania w dashboardzie
(`webapp/static/index.html`) nie działał.

Przyczyna: `index.html` ładował Chart.js z zewnętrznego CDN
(`cdnjs.cloudflare.com`). Na sieci z ograniczonym dostępem do internetu
ten request cicho zawodził, więc `Chart` nigdy nie powstawał. `loadAll()`
odpytywał wszystkie cztery endpointy naraz, ale renderował je *sekwencyjnie
i bez izolacji błędów* — gdy `renderRealBias()` docierał do `new
Chart(...)` i się wywalał, cała reszta funkcji (w tym `renderDemoBias()` i
`renderLatestReadings()`) nigdy się nie wykonywała, a błąd lądował tylko w
konsoli przeglądarki, niewidoczny dla użytkownika. Efekt: kliknięcie
przycisku wyglądało, jakby nic nie robiło.

Naprawione:

1. **Chart.js zwendorowany lokalnie** w `webapp/static/vendor/chart.umd.js`
   (v4.4.4, MIT) zamiast ładowany z CDN — dashboard działa teraz w pełni
   offline.
2. **`loadAll()` przepisany na niezależne sekcje** (`loadSection()`) —
   błąd w jednej sekcji (np. brak Chart.js, błąd sieci, błąd API) nie
   blokuje już renderowania pozostałych trzech, i jest pokazany w
   widocznym żółtym banerze na górze strony zamiast ginąć w konsoli.
3. `app.py`: dodano `app.mount("/static", StaticFiles(...))`, żeby
   zwendorowany plik JS w ogóle dało się serwować.

Testy: `test_index_page_does_not_reference_external_cdn`,
`test_vendored_chartjs_is_served` w `tests/test_webapp.py`.

### Dodano przycisk "▶ Pobierz nowe dane teraz" (2026-08-30)

Po poprawce wyżej zgłoszenie "przycisk dalej nie ładuje danych" wróciło.
Zdiagnozowano: to nie był ten sam błąd, tylko mylący workflow —
"↻ Odśwież teraz" TYLKO na nowo czyta CSV z dysku (zweryfikowano wprost:
dopisanie testowego wiersza do CSV bez restartu serwera natychmiast
pojawiało się w `/api/status` — backend działał poprawnie). Jeśli nikt
wcześniej nie uruchomił `run.bat`/`run_arctic.py` tego dnia, na dysku
faktycznie nie ma nic nowego do przeczytania, więc przycisk wyglądał,
jakby "nic nie robił".

Naprawione przez dodanie DRUGIEGO przycisku, "▶ Pobierz nowe dane teraz",
który faktycznie łączy się z Open-Meteo i dopisuje dane (nowy endpoint
`POST /api/collect`, ta sama funkcja `collect()` co `run_arctic.py`/
`run.bat` — wydzielona do wspólnego miejsca, żeby CLI i przycisk w
przeglądarce robiły identyczną rzecz), a potem sam odświeża widok. Błędy
sieciowe są przechwytywane i pokazane w dashboardzie (`forecast_error`/
`archive_error`), nie ukryte — zweryfikowano wprost: w środowisku bez
dostępu do `api.open-meteo.com` endpoint poprawnie zwraca czytelny błąd
zamiast się wywalać, i NIE dotyka CSV (zero zmian na dysku przy błędzie
sieci).

**Uwaga przy tej okazji**: `run_arctic.py`'s domyślny `CSV_PATH` jest
ŚCIEŻKĄ WZGLĘDNĄ (`"arctic_forecast_snapshots.csv"`) — zależną od
katalogu roboczego procesu. `webapp/app.py` wywołuje `collect()`
z jawną ŚCIEŻKĄ BEZWZGLĘDNĄ (`REAL_CSV`, zakotwiczoną względem
położenia samego pliku `app.py`), żeby wynik nie zależał od tego, skąd
faktycznie wystartował `uvicorn` — potencjalne źródło rozjazdu między
tym, co widzi dashboard, a tym, co zapisał kolektor, gdyby oba czytały
inną kopię pliku.

Pliki: `run_arctic.py` (`collect()` wydzielone z `main()`),
`webapp/app.py` (`POST /api/collect`), `webapp/static/index.html`
(drugi przycisk + `collectNow()`).

### Dopisano testy dla `POST /api/collect` (2026-08-30)

Przegląd kodu wykazał, że nowy endpoint `POST /api/collect` (dodany tego
samego dnia, patrz wyżej) był jedynym endpointem w `webapp/app.py` bez
żadnego testu — wszystkie pozostałe (`/api/status`, `/api/real_bias`,
`/api/demo_bias`, `/api/latest_readings`, nawet regresja na CDN Chart.js)
mają dedykowane testy.

Dodane w `tests/test_webapp.py` (monkeypatch na
`app_module._collect_arctic_data`, żeby nie robić żywego zapytania do
Open-Meteo w CI):

1. `test_collect_endpoint_calls_shared_collect_with_absolute_real_csv` —
   endpoint wywołuje `run_arctic.collect()` z absolutną ścieżką `REAL_CSV`
   i stacją `LONGYEARBYEN`, i zwraca wynik bez zmian.
2. `test_collect_endpoint_passes_through_fetch_errors` —
   `forecast_error`/`archive_error` z `collect()` przechodzą 1:1, endpoint
   nie zamienia ich w błąd 500.

Commit `b45ee3c`. Zaciągnął też wcześniej niezacommitowane zmiany robocze
z tej samej sesji (refaktor `run_arctic.main()` → `collect()`, sam
endpoint, poprawki w dashboardzie).

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

**Status: zweryfikowane na prawdziwej odpowiedzi API 2026-08-27** — parser
zadziałał bez poprawek, zgodnie z udokumentowanym kształtem odpowiedzi.
Wynik pierwszego uruchomienia (90 dni, Longyearbyen, Best Match — jedno
90-dniowe okno jednej stacji arktycznej, nie generalny wniosek o
Open-Meteo):

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
zbieg okoliczności dla tego konkretnego okna/lokalizacji. Liczby będą się
zmieniać przy kolejnych uruchomieniach (inne okno czasowe) — traktować
jako punkt odniesienia, nie stałą.

Testy (`test_previous_runs.py`) nadal używają ręcznie zbudowanego
payloadu (zgodnego z dokumentacją, teraz też potwierdzonego realną
odpowiedzią) — nie zapisano surowej odpowiedzi API jako fixture, bo
`backtest_real.py` był uruchomiony poza tym środowiskiem.

### `demo_synthetic_fill.py` — symulacja, natychmiastowa, w pełni zmyślona

Generuje w pełni sztuczne dane (`demo_synthetic_arctic_snapshots.csv`,
stacja `Longyearbyen_Svalbard_DEMO`) z zamierzonym wzorcem obciążenia
(`bias(lead) = 1.2 − 0.35·lead`) i pokazuje, że `compute_lead_bias()`
poprawnie go odtwarza przy większej próbce (n=90 zamiast n=21 zbliża
wynik do zamierzonych wartości). To demo MECHANIZMU, nie prognoza
niczego o Longyearbyen — każdy wiersz i wydruk jest tagowany `[DEMO]`.
