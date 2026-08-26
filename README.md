# SYNOPTYK-ARCTIC

Wersja Synoptyka dla stacji arktycznej/zdalnej — odpowiedź na pytanie
"czy Synoptyk poradziłby sobie na stacji arktycznej, np. z przerwami w
łączności". Powstaje w dwóch etapach:

1. **Realna stacja arktyczna + uczciwy pomiar trafności** (ten etap — gotowy).
2. **Architektura odporna na przerwy w łączności** (offline-resilient) — w budowie.

## Etap 1 — co jest zrobione i na jakich danych

### Stacja: Longyearbyen, Svalbard

Wybrana jako najbardziej znana, realna lokalizacja arktyczna z publicznie
dostępnymi danymi Open-Meteo. **Sandbox Claude ma zablokowany dostęp do
`api.open-meteo.com` w swoim proxy (403 blocked-by-allowlist)** — więc test
połączenia i pierwsze pobranie wykonał użytkownik na własnym laptopie
2026-08-26. Pliki `tests/fixtures/arctic_*_result.json` to PRAWDZIWE,
niezmienione odpowiedzi API, nie mocki.

Wynik tego testu (`arctic_synoptyk/station.py::LONGYEARBYEN`):

| | żądane | zwrócone przez Open-Meteo |
|---|---|---|
| szerokość | 78.2232 | 78.20738 |
| długość | 15.6267 | 15.697675 |
| wysokość | — | 26.0 m |

Rozjazd (~1.6 km) to normalne przyciągnięcie do najbliższego punktu siatki
modelu globalnego (ECMWF/ICON), nie błąd.

### Różnice metodologiczne vs Synoptyk-v2.0 (Kraków) — świadome, udokumentowane

- **Brak korekty UHI.** "Miejska wyspa ciepła" nie ma zastosowania do
  zdalnej lokalizacji arktycznej — `ArcticStation` w ogóle nie ma pola
  `uhi` (nie: ma je ustawione na 0). Test: `test_station.py::test_longyearbyen_no_uhi_field`.
- **Brak cichego fallbacku dla nieznanej stacji.** `topomap_data.py` w
  Synoptyk-v2.0 dla nieznanej nazwy cicho zwraca `lat=52.0, lon=19.0`
  (środek Polski) — katastrofalne dla Arktyki. Tu nie ma żadnego
  mechanizmu "nazwa → współrzędne z fallbackiem": każda stacja to jawnie
  skonstruowany `ArcticStation`, więc nie da się przypadkiem trafić na
  cichy zły wynik. Test: `test_station.py::test_no_silent_default_for_missing_station`.
- **Dobowy endpoint (`daily=`), nie godzinowy (`hourly=`).** Kraków pobiera
  godzinowe dane i sam agreguje do dobowych (prawdziwa średnia z 24
  punktów). Tu Open-Meteo agreguje dobowo po swojej stronie — prościej,
  ale **`temp_avg_c_approx` to (max+min)/2, NIE prawdziwa średnia dobowa**
  i będzie się systematycznie różnić od niej dla asymetrycznych przebiegów
  temperatury (np. długi, łagodny wieczór a krótki, ostry szczyt w
  południe). Traktować jako przybliżenie, nie tę samą wielkość co `avg_temp_c`
  w Krakowie.
- **Źródło "rzeczywistości" to `archiwum_openmeteo`**, dokładnie ten sam
  status co `OpenMeteo_real_dailymax` w Synoptyk-v2.0 (reanaliza/najlepsze
  dostępne dane, NIE surowy odczyt z fizycznego czujnika stacji — bo żaden
  taki nie jest tu podłączony). To już sprawdzony wzorzec z Krakowa, nie
  nowe założenie.

### Co realnie wiadomo, a czego jeszcze nie

**Wiadomo:** pobieranie działa, zwraca kompletne dane (bez dziur) dla
sierpnia 2026 — 7 dni prognozy + 11 dni archiwum, wszystkie pola obecne
(`test_fetch.py::test_no_missing_values_in_august_fixtures`).

**NIE wiadomo jeszcze:** jaka jest faktyczna trafność prognozy dla tej
stacji. Jedno pobranie z 2026-08-26 dało pierwsze wiersze w
`arctic_forecast_snapshots.csv`, ale `compute_lead_bias()` **celowo zwraca
pusty słownik** — dokładnie tak samo jak Kraków na starcie, zanim zebrało
1236 par w kilka tygodni regularnego uruchamiania. Żeby dostać realny
wynik dla Svalbardu, trzeba uruchamiać `run_arctic.py` (na laptopie, nie w
sandboksie) codziennie przez kilka tygodni — dokładnie ten sam mechanizm
co dla Krakowa, patrz `arctic_synoptyk/bias.py`.

**Też NIE sprawdzone:** zachowanie w okresie nocy polarnej (listopad–luty),
gdzie mogą pojawić się inne wzorce danych/luki niż w sierpniu — obecny
test pokrywa tylko jedno, letnie okno.

## Struktura repo

```
arctic_synoptyk/
    station.py         — ArcticStation (bez UHI, bez cichego fallbacku)
    fetch.py            — pobieranie z Open-Meteo (daily=), parsowanie odpowiedzi
    snapshots.py        — logowanie do CSV (schemat jak krakow_forecast_snapshots.csv)
    bias.py             — bias/MAE per lead_days (identyczna logika co Kraków)
    offline.py          — Etap 2: lokalny bufor, wskaźnik nieaktualności, degradowana estymacja
    connectivity_sim.py — Etap 2: symulacja wielodniowej przerwy w łączności (do testów)
run_arctic.py       — codzienny runner (uruchamiać NA LAPTOPIE, nie w sandboksie)
fetch_arctic_test.py — samodzielny skrypt testowy (bez zależności), którym
                        użytkownik zweryfikował dostęp do API 2026-08-26
arctic_forecast_snapshots.csv — zaseedowane pierwszym realnym pobraniem
tests/            — 28 testów, w tym na PRAWDZIWYCH fixtures z API
```

## Instalacja i uruchomienie

```bash
pip install -r requirements.txt
pytest -v                  # 28 testów, wszystkie na realnych/kontrolowanych danych
python run_arctic.py        # codzienne pobranie + log (URUCHAMIAĆ NA LAPTOPIE)
```

## Status testów

28/28 testów przechodzi — w tym 4 bezpośrednio na prawdziwych odpowiedziach
API z 2026-08-26 (`test_fetch.py`), nie na wymyślonych strukturach.

## Etap 2 — architektura odporna na przerwy w łączności

### Kluczowe rozróżnienie: przyrząd ≠ łączność

Prawdziwa automatyczna stacja arktyczna zwykle ma własne zasilanie
(solar+bateria) i loguje odczyty LOKALNIE cały czas — niezależnie od
tego, czy akurat działa łącze satelitarne (Iridium/Argos), które bywa
niedostępne przez dni czy tygodnie (pogoda, geometria orbity, awaria
nadajnika). `_load_csv_history_fallback()` w Synoptyk-v2.0 nie miało tego
rozróżnienia — zakładało, że brak świeżego Open-Meteo = brak czegokolwiek
świeższego niż ostatnie udane połączenie. Dla Arktyki to złe założenie.

### Co zbudowano

- **`LocalBuffer`** (`offline.py`) — trwały, append-only log odczytów
  (JSONL, nie jeden duży plik JSON — przerwany zapis w połowie nie psuje
  całej historii). Przetrwa restart procesu (test:
  `test_local_buffer_persists_across_instances`).
- **`StalenessLevel`/`classify_staleness()`** — jawny wskaźnik "jak stare
  są dane, na których operujemy", z progami dopasowanymi do realnych
  przerw satelitarnych (🟢 <1 dzień, 🟡 1–3 dni, 🟠 3–14 dni, 🔴 >14 dni) —
  znacznie szersze okno niż niejawne założenie "codziennego internetu" w
  oryginalnym CSV fallbacku Krakowa.
- **`degraded_forecast()`** — gdy nie ma świeżej prognozy z Open-Meteo,
  buduje NAJPROSTSZĄ uczciwą estymację z lokalnego bufora: persystencję
  (ostatni znany odczyt), nie próbę odtworzenia filtru falkowego/SynoptykV4
  na potencjalnie dziurawym sygnale z tygodniowymi przerwami. Wynik zawsze
  zawiera jawny poziom nieaktualności (`staleness`/`staleness_label_pl`),
  więc żaden odbiorca nie dowie się o niepewności danych dopiero z osobnej
  dokumentacji.
- **`connectivity_sim.py`** — symulacja wielodniowej przerwy (nie mam
  dostępu do prawdziwego sprzętu/łącza satelitarnego, żeby to sprawdzić
  inaczej — jawnie przyznane, nie ukryte). Zweryfikowano na symulowanej
  20-dniowej przerwie (`test_connectivity_sim.py`): przyrząd loguje
  wszystkie 25 dni bez wyjątku i utraty danych, wskaźnik nieaktualności
  poprawnie eskaluje FRESH→AGING→STALE→CRITICAL w miarę trwania przerwy, i
  natychmiast wraca do FRESH w dniu przywrócenia łączności.

### Czego ten etap NIE robi (uczciwie, nie domyślnie)

- Nie ma prawdziwej integracji z żadnym sprzętem satelitarnym (Iridium/
  Argos/inny) — `connectivity_sim.py` to symulacja harmonogramu połączeń,
  nie sterownik modemu.
- `degraded_forecast()` nie próbuje ekstrapolować trendu — to świadomy
  wybór (dane z tygodniowymi przerwami są zbyt zawodne dla trendu), nie
  przeoczenie. Rozszerzenie o prostą ekstrapolację (gdy bufor ma
  wystarczająco gęste, nie-dziurawe dane) to możliwy przyszły krok, nie
  zrobiony tutaj.
- Nie ma jeszcze mechanizmu "wyślij zaległe dane po odzyskaniu łączności"
  (`unsynced_since()` już zwraca właściwą listę, ale nic jeszcze jej nie
  konsumuje/wysyła — to następny, nie zrobiony jeszcze krok integracji z
  `snapshots.py`/`bias.py`).
