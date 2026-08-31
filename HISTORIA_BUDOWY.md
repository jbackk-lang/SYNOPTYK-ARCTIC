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

### `backfill_real_history.py` — jak `backtest_real.py`, ale zasila dashboard (2026-08-31)

Zgłoszenie: po 5 dniach zbierania (`run_arctic.py`) dashboard dalej
pokazywał "za mało (n<5)" na każdym `lead_days` — pytanie użytkownika,
czy nie da się tego "załadować" realnymi danymi archiwalnymi, tak jak
SynoptykV4 w Synoptyk-v2.0 liczy od razu na realnej historii zamiast
czekać.

Odpowiedź: taki mechanizm już istniał (`backtest_real.py`, Etap 4 wyżej),
ale tylko drukował wynik na konsolę — nic nie trafiało do
`arctic_forecast_snapshots.csv`, więc dashboard (`/api/real_bias`) o nim
nie wiedział. `backfill_real_history.py` robi to samo pobranie (Previous
Runs API + Archive API), ale dopisuje wynik do CSV przez ten sam
`append_snapshot()` co `run_arctic.py`, pod tymi samymi etykietami
`source` ("prognoza"/"archiwum_openmeteo") — `compute_lead_bias()` i
dashboard widzą go od razu, bez czekania na kolejne dni.

**Decyzja użytkownika (spośród trzech opcji: osobny panel / wpis do
głównego CSV / bez zmian)**: wpisać wprost do głównego CSV pod tymi
samymi etykietami, żeby wynik był widoczny w istniejących panelach bez
nowego endpointu. Świadomy koszt: w przeciwieństwie do reszty projektu
(gdzie dane demo mają zawsze `_DEMO` w nazwie stacji), po samym CSV nie
da się już odróżnić wiersza "zebranego dziś na żywo" od "dociągniętego z
historycznego backfillu" — obie kategorie są jednak PRAWDZIWYMI danymi
Open-Meteo tej samej wielkości (dobowe maksimum), więc uznano to za
akceptowalne uproszczenie, nie za ukrywanie czegoś nieuczciwego.

Implementacja: `build_prognoza_groups()` liczy `issue_date = target_date -
lead_days` dla każdej pary z Previous Runs API i grupuje po `issue_date`
(jedno wywołanie `append_snapshot()` na grupę); wiersze archiwum idą
wprost z `fetch_archive()` z `issue_date=dzisiaj`. Ograniczenie: Previous
Runs API zwraca tylko temperaturę, więc backfillowane wiersze "prognoza"
mają puste `min/avg/precip/pressure/wind` (nie brak danych — po prostu
ich tam nie ma w tym źródle).

Testy: `tests/test_backfill_real_history.py` — grupowanie/przesunięcie
`issue_date` na ręcznie zbudowanym payloadzie (bez żywego zapytania, ten
sam wzorzec co `test_previous_runs.py`), oraz test wprost sprawdzający
cel modułu: jedno wywołanie `backfill()` z 7-dniową próbką daje
`compute_lead_bias()` coś do pokazania natychmiast (bez potrzeby >=5
dni codziennego zbierania), plus test idempotencji (drugie uruchomienie
nie duplikuje wierszy). 55/55 testów przechodzi.

### Retencja CSV: przycinanie do ostatnich 30 dni (2026-08-31)

Po dodaniu `backfill_real_history.py` pytanie użytkownika: skoro CSV
rośnie bezterminowo (codzienne `run_arctic.py` + jednorazowy backfill do
90 dni wstecz), czy nie ustawić mu maksymalnego rozmiaru — "ostatnich 30
dni spokojnie wystarczy do prognozy".

Zweryfikowano matematycznie: `compute_lead_bias()` wymaga >= `min_samples`
(5) sparowanych dni PER `lead_days` (max lead=7). Para dla danego
`lead_days` pojawia się, gdy jej `target_date` ma już >= `lead_days + 2`
dni (odcięcie niesfinalizowanego archiwum). Najdłuższy lead (7) potrzebuje
więc danych sprzed 9 dni — 30-dniowe okno kroczące to ponad 3x zapas.
Potwierdzenie: 30 dni to dokładnie ta sama wartość co
`_CSV_RETENTION_DAYS` już używana w Synoptyk-v2.0
(`gui_app.py::_prune_old_csv_rows`) — nie nowy pomysł, sprawdzony wzorzec.

Implementacja (`arctic_synoptyk/retention.py::prune_old_rows()`) skopiowana
z tego samego wzorca co Krakowa: NIC nie kasuje bezpowrotnie — wiersze
starsze niż `keep_days` (po `target_date`) są NAJPIERW dopisywane do
`arctic_forecast_snapshots_archive.csv` (ten sam układ kolumn, nigdy nie
przycinany), dopiero potem usuwane z pliku gorącego. Różnica względem
Krakowa: tam implementacja używa pandas (`gui_app.py` i tak go importuje);
tu w SYNOPTYK-ARCTIC nie ma pandas w zależnościach (`requirements.txt`:
tylko requests/pytest/fastapi/uvicorn/httpx) — `retention.py` jest więc
napisane na czystym `csv`/stdlib, żeby nie dociągać nowej zależności dla
jednej funkcji.

**Świadoma decyzja o zakresie**: `prune_old_rows()` NIE jest wpięte do
`snapshots.append_snapshot()` (współdzielonej z `demo_synthetic_fill.py`),
tylko wywoływane jawnie z `run_arctic.collect()` i
`backfill_real_history.backfill()` — obie operują na realnym CSV. Powód:
dane demo mają STAŁE, zmyślone daty (start 2026-08-01, niezależne od
prawdziwego "dziś") specjalnie po to, żeby zawsze dawać tę samą, pełną
próbkę (`n_days` argumentu skryptu) do zademonstrowania mechanizmu.
Gdyby retencja działała uniwersalnie w `append_snapshot()`, uruchomienie
`demo_synthetic_fill.py 90` po prostu przycięłoby prawie całą wygenerowaną
próbkę przy najbliższym wywołaniu (2026-08-01 jest dawno starszy niż 30
dni od prawdziwego "dziś"), psując sens demo — złapane PRZED
zaimplementowaniem, nie jako bug naprawiony po fakcie.

**Efekt uboczny na `backfill_real_history.py`**: skoro CSV i tak jest
przycinany do 30 dni, nie ma sensu domyślnie pobierać 90 dni historii —
`DEFAULT_PAST_DAYS` zmienione z 90 na 30 (`= DEFAULT_KEEP_DAYS`,
zaimportowane wprost z `retention.py`, żeby nie rozjechały się przy
przyszłej zmianie). CLI przyjmuje teraz dwa opcjonalne argumenty
(`[liczba_dni] [keep_days]`), żeby świadomie można było pobrać/zatrzymać
dłuższe okno naraz, zamiast pobierać dane, które i tak natychmiast trafią
do archiwum.

Testy: `tests/test_retention.py` (przenoszenie do archiwum, no-op gdy nic
starego, zachowanie wierszy z niesparsowalną datą, dopisywanie do
istniejącego archiwum bez duplikowania nagłówka, zgodność `FIELDNAMES` z
`snapshots.py`), plus po jednym teście wiążącym w
`test_backfill_real_history.py` i nowym `test_run_arctic.py` (ten drugi
przy okazji: `run_arctic.collect()` dostało wstrzykiwalne
`_fetch_forecast`/`_fetch_archive`, tym samym wzorcem co `backfill()` —
wcześniej nie dało się przetestować samej funkcji bez żywego API). 66/66
testów przechodzi.

### Backfill: dołączono wiatr i opad, nie tylko temperaturę (2026-08-31)

Pytanie użytkownika po ustaleniu, że wszystkie parametry pochodzą z
Open-Meteo (internet, nie fizyczny czujnik): skoro tak, to czy wiersze
"prognoza" z backfillu (`backfill_real_history.py`) mogą też mieć wiatr i
opad, nie tylko temperaturę (ograniczenie znane od Etapu 4/backtestu —
Previous Runs API w tym module pytał dotąd wyłącznie o
`temperature_2m_previous_dayN`).

Rozwiązanie: Previous Runs API dokumentuje ten sam wzorzec nazw godzinowych
zmiennych co zwykły `hourly=` endpoint Open-Meteo, z dopiskiem
`_previous_dayN` — to, co już działało dla `temperature_2m`, powinno więc
działać identycznie dla `precipitation` i `wind_speed_10m` (te same nazwy
zmiennych, których `fetch.py`/`hourly=` endpoint już używa gdzie indziej w
projekcie). Rozszerzono:

- `previous_runs.fetch_previous_runs()`: nowy parametr `hourly_vars`
  (domyślnie `("temperature_2m", "precipitation", "wind_speed_10m")`) —
  pyta o wszystkie trzy zmienne × lead_days naraz.
- `previous_runs._aggregate_by_lead()`: wydzielony wspólny rdzeń
  (zmienna godzinowa + funkcja agregująca → dobowa wartość per lead), z
  którego korzystają teraz zarówno stary `daily_max_by_lead()` (tylko
  temperatura, bez zmian w zachowaniu — nadal używane przez
  `backtest_real.py`), jak i nowy `daily_aggregates_by_lead()` (temp+opad+
  wiatr naraz, te same definicje agregacji co `fetch.py`: max dla
  temp/wiatru, suma dla opadu).
- `backfill_real_history.py`: `build_prognoza_groups()`/`_forecast_record()`
  przepisane na słownik wartości zamiast pojedynczej liczby — wypełniają
  teraz `temp_max_c`, `precip_mm` i `wind_kmh` (nadal puste:
  `temp_min_c`/`temp_avg_c_approx`/`pressure_hpa`, bo Previous Runs API nie
  dostarcza min/avg ani ciśnienia w ogóle).

**NIEZWERYFIKOWANE na żywej odpowiedzi API**: w przeciwieństwie do
`temperature_2m_previous_dayN` (potwierdzone realnym zapytaniem
2026-08-27), nazwy `precipitation_previous_dayN`/
`wind_speed_10m_previous_dayN` są wyprowadzone przez analogię do
udokumentowanego wzorca, nie potwierdzone jeszcze realnym payloadem —
sandbox deweloperski nadal ma zablokowany dostęp do
`previous-runs-api.open-meteo.com`. Kod rzuca `KeyError` jawnie, jeśli
któregoś pola zabraknie (ten sam wzorzec co reszta projektu — nie ukrywać
zmiany kształtu odpowiedzi API) — **pierwsze uruchomienie
`backfill_real_history.py` po tej zmianie samo to zweryfikuje**. Jeśli
`KeyError` wyskoczy, to sygnał do poprawienia dokładnej nazwy pola w
`previous_runs.AGGREGATIONS`, nie błąd do zignorowania.

Testy: `tests/test_previous_runs.py` (+3: `daily_aggregates_by_lead()`
łączy trzy zmienne, rzuca `KeyError` przy brakującym polu, stary
`daily_max_by_lead()` nadal działa mimo dodatkowych pól w payloadzie),
`tests/test_backfill_real_history.py` (fixture i asercje przepisane na
słownik wartości, +1 test na brakującą zmienną w jednym dniu — zostaje
pusty string w tej jednej kolumnie, reszta wypełniona). 70/70 testów
przechodzi.

### Dodano kierunek wiatru — nowe pole + migracja CSV (2026-08-31)

Po dołączeniu opadu i wiatru do backfillu użytkownik zapytał o kierunek
wiatru w tabeli "Surowe odczyty" dashboardu — z prośbą o "grubą
strzałeczkę, tak jak w zwykłym synoptyku" (Synoptyk-v2.0). W odróżnieniu
od poprzedniej zmiany (dodanie kolumn do WIDOKU, dane już były w CSV), to
było faktycznie nowe pole — projekt nigdy nie zbierał kierunku wiatru.

**Zmiana schematu CSV** — pierwsza w tym projekcie. `wind_direction_deg`
dodane do `snapshots.FIELDNAMES`/`retention.FIELDNAMES` (między
`wind_kmh` a `source`) — **wymagało migracji** trzech istniejących plików
(`arctic_forecast_snapshots.csv` — 309 wierszy prawdziwych danych,
`arctic_forecast_snapshots_archive.csv` — 480, `demo_synthetic_arctic_snapshots.csv`
— 726): każdy przepisany z 11- na 12-kolumnowy nagłówek, istniejące
wiersze dostały pusty `wind_direction_deg` (nie mają tej wartości —
zbierana od teraz, nie retrospektywnie). Bez tej migracji kolejny
`append_snapshot()` dopisałby wiersze o innej liczbie pól niż nagłówek
pliku — cichy, trudny do zdiagnozowania błąd struktury CSV.

**Źródło danych — dwa różne poziomy zaufania**:
- `run_arctic.py`/`fetch_archive()`/`fetch_forecast()` (`fetch.py`):
  Open-Meteo ma bezpośrednią dobową zmienną
  `wind_direction_10m_dominant` — serwer sam liczy poprawny "dominujący
  kierunek", nie musimy nic agregować. Dodane do `_DAILY_FIELDS`, pole
  OPCJONALNE (`.get()`, nie `[...]`) w `_parse_daily_response()` — jedyny
  wyjątek od reguły "wszystkie pola wymagane na sztywno" w tym module, bo
  dwa zapisane fixture'y (`tests/fixtures/arctic_*_result.json`, z
  2026-08-26) legalnie go nie mają — zostały zapisane, zanim to pole
  dołączyło do zapytania.
- `backfill_real_history.py` (Previous Runs API): **ŚWIADOMIE NIE
  dodane**. Kierunek wiatru to wielkość kołowa — zwykła średnia/max z
  wartości w stopniach daje fizycznie błędny wynik blisko granicy 0/360
  (np. średnia z 350° i 10° to 0°, nie 180° — dokładnie ten sam problem,
  który Synoptyk-v2.0 rozwiązuje `_circular_mean_deg()`, średnią
  wektorową). Naiwne zastosowanie tej samej agregacji co dla
  temp/opad/wiatru (max/suma) na godzinowym sygnale z Previous Runs API
  dawałoby błędne wyniki właśnie tam, gdzie kierunek przechodzi przez
  północ. Zamiast zgadywać uproszczoną metodę, `wind_direction_deg`
  zostaje pusty dla wszystkich backfillowanych wierszy "prognoza" — ten
  sam wybór co dla `temp_min_c`/`temp_avg_c_approx`/`pressure_hpa`, które
  Previous Runs API w ogóle nie dostarcza.

**Wyświetlanie**: dashboard renderuje pojedynczą strzałkę (jedną z 8:
↑↗→↘↓↙←↖, pokazującą DOKĄD wieje wiatr, nie skąd) — **identyczna logika
co `gui_app.py::_WIND_ARROWS`/`_wind_arrow()` w Synoptyk-v2.0**
(przeportowana 1:1 do JS: `deg_to = (deg_from + 180) % 360`, indeks =
`((deg_to + 22.5) % 360) // 45`), tylko wyraźnie pogrubiona/powiększona
(klasa `.wind-arrow`, `font-size: 18px; font-weight: 700`) na życzenie
użytkownika ("gruba strzałeczka"). Stopnie pokazane w `title` (hover),
jeśli ktoś chce dokładną wartość, nie tylko kierunek w przybliżeniu.

Testy: `tests/test_fetch.py` (+2: fixture'y z 2026-08-26 legalnie nie
mają pola → `None`, ręcznie zbudowany payload z polem → poprawnie
sparsowane), `tests/test_webapp.py` (+1: strzałka i klasa CSS w
wyrenderowanym HTML, ten sam wzorzec co test na kolumny opadu/wiatru).
74/74 testów przechodzi.

### `demo_synthetic_fill.py` — symulacja, natychmiastowa, w pełni zmyślona

Generuje w pełni sztuczne dane (`demo_synthetic_arctic_snapshots.csv`,
stacja `Longyearbyen_Svalbard_DEMO`) z zamierzonym wzorcem obciążenia
(`bias(lead) = 1.2 − 0.35·lead`) i pokazuje, że `compute_lead_bias()`
poprawnie go odtwarza przy większej próbce (n=90 zamiast n=21 zbliża
wynik do zamierzonych wartości). To demo MECHANIZMU, nie prognoza
niczego o Longyearbyen — każdy wiersz i wydruk jest tagowany `[DEMO]`.

## Strzałka kierunku wiatru: styl i luka po idempotentności (2026-08-31)

**Styl**: użytkownik zobaczył pogrubioną/powiększoną strzałkę
(`font-size: 18px; font-weight: 700`, patrz wyżej) na żywym dashboardzie
i ocenił ją jako za grubą ("dashboard nie przyjmuje tej formy"). Wraca
do zwykłego stylu tekstu tabeli, zostawiając tylko `color: var(--accent)`
do odróżnienia od reszty kolumn. Sam znak i logika wyboru strzałki
(`_wind_arrow`/`windArrow`) bez zmian — to czysto kosmetyczna korekta.

**Luka danych, zgłoszona zaraz potem**: po zmianie stylu użytkownik
zauważył, że kolumna "kier." nadal pokazuje same "—" mimo kliknięcia
"Pobierz nowe dane teraz". Przyczyna: `wind_direction_10m_dominant`
dołączyło do `_DAILY_FIELDS` w `fetch.py` tego samego dnia
(2026-08-31), ale `append_snapshot()` jest idempotentne po kluczu
`(station, target_date, issue_date, source)` — wiersze na dziś zostały
zapisane (przez wcześniejsze uruchomienia tego samego dnia, sprzed
zmiany) PRZED dodaniem pola, więc klucz już istniał i kolejne pobrania
z tym samym `issue_date` były po prostu pomijane jako duplikaty — razem
z ich (teraz dostępnym) kierunkiem wiatru. Bez naprawy kolumna
zostałaby pusta aż do jutra (nowy `issue_date` = nowy klucz).

Naprawa w `snapshots.py::append_snapshot()`: gdy klucz już istnieje w
CSV, ale jego `wind_direction_deg` jest puste, a nowo pobrany rekord
faktycznie ma tę wartość — dopisujemy ją do ISTNIEJĄCEGO wiersza
zamiast pomijać go w ciszy (funkcja przeszła z trybu "append-only" na
"czytaj cały CSV, uzupełnij/dopisz, zapisz cały plik" — bezpieczne przy
30-dniowej retencji, plik jest mały). Uzupełnianie działa tylko w jedną
stronę (nigdy nie nadpisuje już zapisanej realnej wartości nową) i nie
wlicza się do zwracanego `n` nowych wierszy — to nie jest nowy wiersz,
tylko domknięcie starego. Ten sam mechanizm samoczynnie naprawi
analogiczną lukę dla każdego przyszłego "miękkiego" pola dodanego w
środku dnia zbierania.

Testy (+2, `tests/test_snapshots.py`): uzupełnienie pustego pola na
istniejącym kluczu bez duplikowania wiersza, oraz dowód że realna
wartość nigdy nie jest nadpisywana kolejnym pobraniem. 76/76 testów
przechodzi.

**Do zrobienia lokalnie**: to wymaga jeszcze jednego uruchomienia
`python run_arctic.py` albo kliknięcia "Pobierz nowe dane teraz" na
prawdziwym API (sandbox nie ma dostępu do `api.open-meteo.com`) — dopiero
wtedy dzisiejsze wiersze faktycznie dostaną kierunek wiatru.

**Efekt uboczny naprawy**: proces uvicorn trzeba było zrestartować, żeby
podjął nowy kod (`fetch.py`/`snapshots.py` w pamięci procesu nie
przeładowują się same) — po restarcie kierunek zaczął się faktycznie
pokazywać. Użytkownik poprosił wtedy o powrót do pogrubionej strzałki
(bez zwiększania rozmiaru tym razem, żeby nie powtórzyć poprzedniego
"za grubo") - `.wind-arrow { font-weight: 700 }`, bez zmiany rozmiaru.

## Wiele stacji: 6 nowych + przełącznik w dashboardzie (2026-08-31)

Użytkownik poprosił o "stacje arktyczne 3-5 najważniejszych", potem
doprecyzował: koniecznie Polska Stacja Polarna Hornsund ("i polska na
wyspie"), a w kolejnej turze wybrał WSZYSTKIE 4 zaproponowane kandydatury
(Ny-Ålesund, Alert, Utqiagvik, Tiksi) plus dorzucił przez pole "Other"
"Polska arctowski" — czyli Polską Stację Antarktyczną im. Henryka
Arctowskiego, potwierdzoną linkiem do arctowski.aq. Finalnie: **7 stacji**
łącznie z Longyearbyen, nie 3-5 — świadome rozszerzenie zakresu przez
użytkownika w trakcie rozmowy, nie błąd interpretacji.

**Współrzędne/wysokości** zweryfikowane wyszukiwaniem (Wikipedia, NOAA
GML, strona IGF PAN, arctowski.aq) 2026-08-31 — NIE pomiarem w tym repo,
w odróżnieniu od `LONGYEARBYEN.grid_lat`/`grid_lon`/`grid_elevation_m`
(te trzy pola u nowych stacji zostają `None`, dopóki nie padnie pierwszy
żywy fetch — patrz "Znane ograniczenia" w README).

**Arctowski = Antarktyda, nie Arktyka**: świadomie zaakceptowany wyjątek
od nazwy projektu ("SYNOPTYK-ARCTIC"), NIE pomyłka nazewnicza — druga
(obok Hornsund) polska całoroczna stacja polarna, więc naturalnie pasuje
do zestawienia "polskie stacje polarne" mimo złamania założenia "tylko
Arktyka". Konsekwencje odnotowane w dwóch miejscach: (1) nazwa stacji w
kodzie/CSV/dashboardzie to dosłownie `Arctowski_Antarktyda` (nie sam
"Arctowski") - fakt widoczny wszędzie, gdzie nazwa się pojawia, bez
potrzeby czytania komentarza w kodzie; (2) dashboard pokazuje jawne
ostrzeżenie pod nagłówkiem, gdy ta stacja jest wybrana ("PÓŁKULA
POŁUDNIOWA — pory roku odwrócone"), bo "noc polarna listopad-luty" z
README/`Znane ograniczenia` dotyczy wyłącznie półkuli północnej i byłaby
myląca zastosowana tu wprost.

**Architektura — jedna zmiana wystarczyła w rdzeniu**: `snapshots.py`
(`append_snapshot`) i `bias.py` (`compute_lead_bias`) od SAMEGO POCZĄTKU
przyjmowały `station_name` jako parametr i filtrowały po kolumnie
`station` w CSV — więc wiele stacji na jednym, wspólnym pliku CSV
zadziałało bez zmiany schematu ani żadnej z tych dwóch funkcji. Realna
praca: `station.py` (nowe stałe `ArcticStation` + `STATIONS`/
`STATIONS_BY_NAME`), `run_arctic.py` (`collect_all()` — pętla po
`STATIONS`, wspólny CSV, `main()` drukuje wynik per stacja),
`backfill_real_history.py` (`main()` analogicznie zapętlony, błąd sieci
dla jednej stacji nie przerywa reszty — ważne dla Arctowskiego, inny
region/serwer Open-Meteo niż reszta), `webapp/app.py` (`GET /api/stations`
+ `?station=` na czterech pozostałych endpointach, `_resolve_station()`
zwraca HTTP 404 na nieznaną nazwę zamiast cichego fallbacku — ten sam
duch co brak fallbacku w `station.py` dla nieznanej nazwy stacji),
`index.html` (dropdown w nagłówku, `currentStation` + `_withStation()`
dokleja `?station=` do wywołań status/real_bias/latest_readings/collect;
`/api/demo_bias` CELOWO bez tego parametru — demo to zawsze jedna, stała
stacja syntetyczna, niezależna od wyboru na dashboardzie).

**Wsteczna zgodność**: brak `?station=` = domyślnie Longyearbyen
(`DEFAULT_STATION`) na wszystkich endpointach — dokładnie po to, żeby
`tests/test_webapp.py` sprzed tej zmiany (odpytujące endpointy bez
parametru) przeszły bez modyfikacji. `POST /api/collect` przestał zawsze
wołać `LONGYEARBYEN` na sztywno — teraz zbiera dla stacji z `?station=`
(albo domyślnej), JEDNEJ na kliknięcie (nie wszystkich 7 naraz — zbieranie
wszystkiego naraz robi `run_arctic.py`/`collect_all()`, osobno).

Testy (+12): `test_station.py` (rejestr 7 stacji, unikalność nazw,
Arctowski jako jedyny wyjątek `lat<0`), `test_run_arctic.py`
(`collect_all()` na wspólnym CSV, domyślnie cały `STATIONS`),
`test_webapp.py` (`/api/stations`, filtrowanie `?station=`, 404 na
nieznaną nazwę, `/api/collect` na wybranej stacji, nie zawsze
Longyearbyen). 88/88 testów przechodzi.

## Jeszcze 3 stacje antarktyczne + grupowanie Północ/Południe + domyślna Hornsund (2026-08-31)

Po zgłoszeniu "dane archiwalne się nie ładują bo druga półkula?" dla
Arctowskiego — zdiagnozowane jako fałszywy trop: Open-Meteo Archive API
nie ma ograniczenia półkulowego, prawdziwa przyczyna to zwykły brak
zebranych jeszcze danych dla nowo dodanej stacji (backfill trzeba było
uruchomić ponownie po dodaniu stacji do rejestru) — nie osobny bug per
półkula. Przy okazji użytkownik zapytał, czy są inne uznane stacje
antarktyczne poza Arctowskim — tak, dołożone 3: **McMurdo** (USA,
największa stacja na Antarktydzie), **Amundsen-Scott** (USA, dokładnie na
biegunie południowym — długość geograficzna tam matematycznie
nieokreślona, przyjęto konwencjonalne 0°E), **Wostok** (Rosja, miejsce
najniższej zarejestrowanej temperatury na Ziemi, -89.2°C).

**Grupowanie Północ/Południe**: `ArcticStation` dostał `@property
hemisphere` liczone WPROST ze znaku `lat` (nie osobne, ręcznie wpisywane
pole — jedno źródło prawdy, nie da się rozjechać przy kolejnej stacji).
`STATIONS_NORTH`/`STATIONS_SOUTH` w `station.py` to filtrowanie po tej
property. `GET /api/stations` zwraca teraz `north`/`south` obok pełnej
`stations` — dashboard buduje z nich dwa `<optgroup>` (🧭 Północ / 🧊
Południe) zamiast liczyć grupowanie samodzielnie w JS. Ostrzeżenie o
odwróconych porach roku na dashboardzie (dodane przy Arctowskim) zostało
poprawione — sprawdzało wcześniej `nazwa.includes("Antarktyda")`, co
pomijałoby Amundsen-Scott (`Amundsen_Scott_Biegun_Poludniowy`, bez tego
słowa w nazwie); teraz sprawdza `hemisphere === "S"` z `/api/status`,
więc działa dla KAŻDEJ stacji południowej, nie tylko tych z konkretnym
słowem w nazwie.

**Domyślna stacja zmieniona na Hornsund** (użytkownik: "ustaw polska jako
domyślna") — spośród dwóch polskich stacji wybrany Hornsund (Arktyka), nie
Arctowski (Antarktyda): lepiej pasuje do nazwy/tematu projektu
(SYNOPTYK-ARCTIC) i to on padł jako pierwszy w rozmowie o polskich
stacjach ("i polska na wyspie", zanim doszło do Arctowskiego). Jeśli to
zła interpretacja "polska" (dwie stacje kwalifikują się), łatwo zmienić
`DEFAULT_STATION` w `webapp/app.py` na `ARCTOWSKI.name`.

**Testy przepisane pod nową wartość domyślną**: testy w `test_webapp.py`,
które wcześniej polegały na tym, że brak `?station=` trafia w
Longyearbyen (bo to była wtedy wartość domyślna), teraz albo (a) jawnie
doklejają `?station=Longyearbyen_Svalbard`, gdy chodzi im o "jakąś
konkretną stację, wszystko jedno którą" — żeby nie rozjeżdżały się przy
KOLEJNEJ zmianie domyślnej, albo (b) sprawdzają wprost przeciw nowej
stałej `DEFAULT_STATION = "Hornsund_Polska_Stacja_Polarna"`, gdy
PRZEDMIOTEM testu jest sama wartość domyślna (`test_status_no_data_yet`,
`test_status_filters_by_station_param`, `test_stations_endpoint_lists_full_registry`).

Testy (+3 netto, kilka przepisanych): rejestr rozszerzony do 10 stacji
(6 północ / 4 południe), `hemisphere` per stacja, `/api/stations` zwraca
poprawnie pogrupowane `north`/`south`, nowa wartość `DEFAULT_STATION`.
88/88 przechodzi.

## Panel "Prognoza 7 dni" (2026-08-31)

Użytkownik zapytał: meteoblue dla Arctowskiego pokazuje ostre ochłodzenie
w środku tygodnia — czy nasz dashboard to w ogóle wyłapuje? Sprawdzone
bezpośrednio na realnych danych już zebranych w `arctic_forecast_snapshots.csv`
(issue_date 2026-08-31, kolektor uruchomiony lokalnie przez użytkownika):
temp_max_c spada z -0.1°C (31.08) do -10.3°C (02.09), potem wraca do
-0.6°C (06.09) — po przeliczeniu na wspólną jednostkę różnica względem
meteoblue to max ~1.2°C na każdym dniu (normalny rozrzut między
modelami: Open-Meteo best-match vs własny blend meteoblue). **Dane były
poprawne od początku** — problem był w prezentacji, nie w kolekcji: nie
istniał żaden panel pokazujący "prognoza dzień po dniu", tylko płaska
lista ostatnich wierszy (`/api/latest_readings`, miesza źródła i
`issue_date`) i wsteczny wykres bias/MAE.

Przed wdrożeniem pokazana makieta (`mcp__visualize`) z DOKŁADNIE tymi
realnymi liczbami Arctowskiego, żeby odpowiedzieć na pytanie "czy to
będzie czytelne i coś daje" empirycznie, nie deklaratywnie — dopiero po
akceptacji makiety wbudowane na stałe.

**`GET /api/forecast_outlook?station=`** (`webapp/app.py`): filtruje
`source="prognoza"` do JEDNEGO, najświeższego `issue_date` (max po
stringu ISO — leksykograficznie poprawne), sortuje po `target_date`
rosnąco. Puste `days: []` (nie 404/500) gdy nic jeszcze nie zebrano - ten
sam wzorzec co pozostałe endpointy.

**Panel w `index.html`**: SVG rysowany ręcznie w JS z wartości danych
(nie Chart.js) — bo Chart.js nie da się łatwo dopasować do istniejącego
`--panel`/`--accent`/ciemnego motywu bez dorzucania kolejnej biblioteki
tylko dla dwóch linii. Pasmo (`polygon`) między max/min + dwie linie +
tabela z tymi samymi wartościami (dostępność/czytelność dla kogoś, kto
woli liczby od wykresu). Odznaka `⚠️ ochłodzenie/ocieplenie ±N°C` pojawia
się, gdy dzień-do-dnia skok `temp_max_c` wynosi ≥5°C — to bezpośrednia,
widoczna odpowiedź na pytanie "czy synoptyk wyłapuje ostrą zmianę",
liczona z tych samych danych co wykres, nie osobna logika.

Testy (+5, `test_webapp.py`): pusty wynik bez danych, wybór WYŁĄCZNIE
najświeższego `issue_date` + sortowanie mimo losowej kolejności zapisu w
CSV + pominięcie wierszy "archiwum" i starszych `issue_date`, filtrowanie
po `?station=`, 404 na nieznaną stację, obecność panelu w wyrenderowanym
HTML. 93/93 przechodzi.
