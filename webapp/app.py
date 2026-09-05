"""
webapp/app.py — lokalna appka (FastAPI) dla SYNOPTYK-ARCTIC.

Świadomy wybór po rozmowie z użytkownikiem: NIE statyczny HTML z wbudowanymi
danymi (trzeba by regenerować po każdym `run_arctic.py`), NIE plik JSON+
lokalny serwer plików tylko-do-serwowania - tylko prawdziwa mała appka,
która przy KAŻDYM żądaniu na nowo czyta aktualne CSV z dysku. Dane są więc
zawsze aktualne bez żadnego kroku regeneracji.

Endpointy:
- GET  /              — strona dashboardu (statyczny HTML + JS, który sam
                         odpytuje endpointy JSON poniżej przy każdym
                         załadowaniu/odświeżeniu strony)
- GET  /api/status     — metadane stacji, ile wierszy realnych danych,
                         data ostatniego pobrania, poziom nieaktualności
                         (classify_staleness na PRAWDZIWEJ dacie ostatniego
                         wiersza, nie na fikcyjnym zegarze)
- GET  /api/real_bias  — compute_lead_bias() na PRAWDZIWYM
                         arctic_forecast_snapshots.csv (min_samples=5,
                         czyli pusto/niepełno, dopóki się nie zbierze -
                         plus surowe liczniki n per lead_days dla
                         przejrzystości, jawnie opisane jako "nieoficjalne")
- GET  /api/demo_bias  — to samo, ale na demo_synthetic_arctic_snapshots.csv
                         (SYNTETYCZNE dane) - zawsze jawnie opisane jako
                         demo, nigdy nie miesza się z /api/real_bias
- GET  /api/resonance  — calibrate_resonance() (arctic_synoptyk/
                         resonance_calibration.py) na PRAWDZIWYM
                         arctic_forecast_snapshots.csv: czy dni oflagowane
                         jako "rezonansowe" (proxy z temp_max_c/
                         pressure_hpa/precip_mm/wind_kmh, patrz
                         arctic_synoptyk/resonance.py) faktycznie miały
                         wyższy błąd prognozy. status="insufficient_data"
                         (confidence_multiplier zostaje 1.0) jest
                         OCZEKIWANYM, częstym stanem większości stacji -
                         patrz docstring resonance_calibration.py (10
                         stacji, 30-dniowa retencja CSV) - nigdy nie
                         udajemy skalibrowanego wyniku na garstce danych.
- GET  /api/latest_readings — SUROWE, NIESPAROWANE wiersze z REAL_CSV (i
                         "prognoza", i "archiwum_openmeteo"), posortowane
                         od najnowszych. Cel: dać widoczność, że kolektor w
                         ogóle działa i zapisuje realne liczby, zanim
                         uzbiera się >= min_samples par potrzebnych do
                         /api/real_bias - bez tego endpointu jedyny sposób
                         sprawdzenia "czy coś się zbiera" to zajrzenie do
                         CSV ręcznie na dysku.
- GET  /api/forecast_outlook — NAJNOWSZE wiersze "prognoza" (jeden
                         issue_date - ostatni, dla ktorego cokolwiek
                         zebrano), posortowane po target_date rosnaco -
                         "prognoza na kolejne dni" w stylu tygodniowki
                         meteoblue, nie plaska lista jak /api/latest_readings
                         (patrz "Prognoza 7 dni" nizej - dodane po pytaniu
                         uzytkownika, czy dashboard w ogole wylapuje ostra
                         zmiane pogody widoczna na meteoblue dla Arctowskiego
                         - dane juz to lapaly, tylko nie bylo tego widac).
- POST /api/collect    — URUCHAMIA faktyczne pobranie nowych danych z
                         Open-Meteo i dopisanie do CSV (to samo, co
                         `python run_arctic.py`/`run.bat`, ta sama funkcja
                         `collect()`) - patrz uwaga niżej, DLACZEGO to
                         osobny przycisk od "Odśwież teraz".

Ścieżki do plików CSV są modułowymi stałymi (REAL_CSV/DEMO_CSV) właśnie po
to, żeby testy mogły je podmienić (monkeypatch) na izolowane pliki
tymczasowe - appka nigdy nie pisze do CSV, tylko czyta, więc to bezpieczne.

## Wiele stacji (dodane 2026-08-31)

`/api/status`, `/api/real_bias`, `/api/latest_readings` i `POST /api/collect`
przyjmują teraz opcjonalny query param `?station=<nazwa>` (patrz
`arctic_synoptyk.station.STATIONS_BY_NAME` - dokładnie te same nazwy, co w
kolumnie `station` w CSV). Brak parametru = domyślnie `DEFAULT_STATION`
(Hornsund, Polska Stacja Polarna — ustawione tak na wyraźną prośbę
użytkownika 2026-08-31, patrz HISTORIA_BUDOWY.md) - endpointy nadal
działają identycznie dla dowolnej innej stacji, tylko domyślna zmieniła
się z Longyearbyen na Hornsund.
Nieznana nazwa stacji -> HTTP 404 (jawny błąd, nie cichy fallback - ten
sam wzorzec co `ArcticStation`/`station.py`, patrz tamten docstring o
`topomap_data.py` w Synoptyk-v2.0). Nowy `GET /api/stations` daje
frontendowi listę wszystkich stacji do zbudowania dropdowna, bez
duplikowania jej w JS.

## Prognoza 7 dni (dodane 2026-08-31)

`/api/latest_readings` istniał od początku, ale jest to płaska lista
OSTATNICH N wierszy (miesza "prognoza" i "archiwum_openmeteo", różne
issue_date) - dobra do "czy kolektor w ogóle coś zapisuje", zła do "jak
wygląda tydzień naprzód" (trzeba by ręcznie wyławiać wzrokiem wiersze
jednego issue_date z natłoku innych). `GET /api/forecast_outlook`
odpowiada wprost na to drugie pytanie - bierze TYLKO najświeższy
issue_date źródła "prognoza" i zwraca go posortowany po target_date
rosnąco, gotowe do narysowania jako wykres/tabela "dziś -> +6 dni".

Powód dodania: użytkownik zapytał, czy dashboard w ogóle wyłapuje ostrą
zmianę pogody widoczną w tym samym czasie na meteoblue dla Arctowskiego.
Odpowiedź (patrz HISTORIA_BUDOWY.md) była "dane TAK, ale dashboard tego
nie pokazywał czytelnie" - surowe wiersze były w CSV (Open-Meteo, ten sam
kolektor co reszta), tylko żaden panel nie prezentował ich jako "tydzień
naprzód".
"""
from __future__ import annotations

import csv as _csv
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from arctic_synoptyk.bias import compute_lead_bias
from arctic_synoptyk.offline import classify_staleness
from arctic_synoptyk.resonance_calibration import calibrate_resonance
from arctic_synoptyk.station import LONGYEARBYEN, HORNSUND, STATIONS, STATIONS_BY_NAME, STATIONS_NORTH, STATIONS_SOUTH
from run_arctic import collect as _collect_arctic_data

BASE_DIR = Path(__file__).resolve().parent.parent
REAL_CSV = BASE_DIR / "arctic_forecast_snapshots.csv"
DEMO_CSV = BASE_DIR / "demo_synthetic_arctic_snapshots.csv"
DEFAULT_STATION = HORNSUND.name  # zmienione z Longyearbyen 2026-08-31, na
# wyrazna prosbe uzytkownika ("ustaw polska jako domyslna") - patrz
# HISTORIA_BUDOWY.md. Hornsund (Polska Stacja Polarna, Arktyka) wybrany
# nad Arctowski (rowniez polska, ale Antarktyda) bo lepiej pasuje do
# nazwy/tematu projektu (SYNOPTYK-ARCTIC) i to ta stacja padla jako
# pierwsza w rozmowie o polskich stacjach.
STATION = DEFAULT_STATION  # zachowane dla wstecznej zgodnosci (patrz nizej)
DEMO_STATION = "Longyearbyen_Svalbard_DEMO"
MIN_SAMPLES = 5


def _resolve_station(station: str | None):
    """`?station=` -> ArcticStation, albo DEFAULT_STATION gdy brak param.
    Nieznana nazwa -> 404 jawnie (patrz "Wiele stacji" w docstringu
    modulu) - zamiast cicho spasc na domyslna stacje, co ukrywaloby literowke
    w URL/froncie."""
    name = station or DEFAULT_STATION
    if name not in STATIONS_BY_NAME:
        raise HTTPException(status_code=404, detail=f"Nieznana stacja: {name!r}")
    return STATIONS_BY_NAME[name]

app = FastAPI(title="SYNOPTYK-ARCTIC Dashboard")

# Serwuje webapp/static/vendor/chart.umd.js pod /static/vendor/... . Wczesniej
# index.html ladowal Chart.js z cdnjs.cloudflare.com - na sieci firmowej z
# ograniczonym dostepem do internetu ten request cicho zawodzil, `Chart`
# nigdy nie powstawal, a przycisk "Odswiez teraz" wygladal jakby nic nie
# robil (loadAll() wywalal sie w polowie na `new Chart(...)`, zanim zdazyl
# zaktualizowac pozostale panele). Teraz caly dashboard dziala bez internetu.
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _read_rows(csv_path: Path, station: str) -> list[dict]:
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    return [r for r in rows if r.get("station") == station]


@app.get("/api/stations")
def stations() -> dict:
    """Lista wszystkich stacji (nazwa + wspolrzedne + polkula) do
    zbudowania dropdowna w dashboardzie - patrz "Wiele stacji" w
    docstringu modulu. `hemisphere` ("N"/"S", liczone z lat - patrz
    ArcticStation.hemisphere) pozwala frontendowi pogrupowac liste na
    dwa optgroup (Polnoc/Poludnie) bez duplikowania logiki grupowania
    po stronie JS."""
    def _as_dict(s):
        return {"name": s.name, "lat": s.lat, "lon": s.lon, "hemisphere": s.hemisphere}

    return {
        "stations": [_as_dict(s) for s in STATIONS],
        "north": [_as_dict(s) for s in STATIONS_NORTH],
        "south": [_as_dict(s) for s in STATIONS_SOUTH],
        "default": DEFAULT_STATION,
    }


@app.get("/api/status")
def status(station: str | None = None) -> dict:
    st = _resolve_station(station)
    rows = _read_rows(REAL_CSV, st.name)
    issue_dates = sorted({r["issue_date"] for r in rows if r.get("issue_date")})
    last_issue_date = issue_dates[-1] if issue_dates else None

    staleness = None
    staleness_label = None
    if last_issue_date:
        last_dt = datetime.fromisoformat(last_issue_date).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        level = classify_staleness(last_dt, now)
        staleness = level.value
        staleness_label = level.label_pl

    return {
        "station": st.name,
        "lat": st.lat,
        "lon": st.lon,
        "hemisphere": st.hemisphere,
        "n_rows_real": len(rows),
        "n_days_collected": len(issue_dates),
        "last_issue_date": last_issue_date,
        "staleness": staleness,
        "staleness_label_pl": staleness_label,
        "min_samples_required": MIN_SAMPLES,
    }


@app.get("/api/real_bias")
def real_bias(station: str | None = None) -> dict:
    st = _resolve_station(station)
    official = compute_lead_bias(str(REAL_CSV), st.name, min_samples=MIN_SAMPLES)
    raw = compute_lead_bias(str(REAL_CSV), st.name, min_samples=1)
    return {
        "official": official,
        "raw_counts": {lead: v["n"] for lead, v in raw.items()},
        "min_samples": MIN_SAMPLES,
        "note": (
            "official = tylko lead_days z >= min_samples sparowanymi dniami "
            "(prognoza, rzeczywistość) - puste na starcie, to oczekiwane, nie "
            "błąd. raw_counts to WYŁĄCZNIE liczba dotychczas zebranych par per "
            "lead_days, do śledzenia postępu - NIE traktować jako wynik trafności."
        ),
    }


@app.get("/api/resonance")
def resonance(station: str | None = None) -> dict:
    """calibrate_resonance() na PRAWDZIWYM REAL_CSV dla wybranej stacji -
    patrz "Endpointy" w docstringu modulu i arctic_synoptyk/
    resonance_calibration.py po pelny opis kontraktu uczciwosci
    (status="insufficient_data" -> confidence_multiplier zostaje 1.0,
    nigdy udawanej kalibracji). Nieznana stacja -> 404, ten sam wzorzec
    co pozostale endpointy `?station=` w tym pliku."""
    st = _resolve_station(station)
    result = calibrate_resonance(str(REAL_CSV), st.name)
    result["station"] = st.name
    result["note"] = (
        "PROXY rezonansu liczony z kanalow temp_max_c/pressure_hpa/"
        "precip_mm/wind_kmh (brak wilgotnosci - ten CSV jej nie loguje). "
        "status='insufficient_data' jest oczekiwanym, czestym stanem przy "
        "malej liczbie sparowanych dni na stacje (30-dniowa retencja CSV, "
        "10 stacji dzielacych limity API) - NIE oznacza bledu."
    )
    return result


@app.get("/api/demo_bias")
def demo_bias() -> dict:
    if not DEMO_CSV.exists():
        return {
            "error": "brak pliku demo - uruchom `python demo_synthetic_fill.py`",
            "bias": {},
        }
    result = compute_lead_bias(str(DEMO_CSV), DEMO_STATION, min_samples=MIN_SAMPLES)
    return {
        "bias": result,
        "station": DEMO_STATION,
        "disclaimer": (
            "DANE SYNTETYCZNE - demo mechanizmu compute_lead_bias(), "
            "NIE pomiar rzeczywistej trafności stacji arktycznej."
        ),
    }


@app.get("/api/latest_readings")
def latest_readings(limit: int = 20, station: str | None = None) -> dict:
    """Surowe wiersze z REAL_CSV (obu źródeł - "prognoza" i
    "archiwum_openmeteo"), posortowane malejąco po (issue_date, target_date).

    Celowo NIE wymaga sparowania prognoza<->rzeczywistość ani min_samples -
    to jest widok "czy pipeline żyje", nie widok trafności. Jeśli tu coś
    się pokazuje, kolektor faktycznie pisze dane; brak wpisów dla
    lead_days=0 w /api/real_bias to wtedy potwierdzone kwestia progu/
    opóźnienia archiwum, a nie tego, że nic się nie zbiera."""
    st = _resolve_station(station)
    rows = _read_rows(REAL_CSV, st.name)
    rows_sorted = sorted(
        rows,
        key=lambda r: (r.get("issue_date", ""), r.get("target_date", "")),
        reverse=True,
    )
    return {"rows": rows_sorted[:limit], "n_total": len(rows)}


@app.get("/api/forecast_outlook")
def forecast_outlook(station: str | None = None) -> dict:
    """Najnowsza prognoza "dzien po dniu" dla wybranej stacji - patrz
    "Prognoza 7 dni" w docstringu modulu po pelne uzasadnienie.

    Bierze WYLACZNIE source="prognoza" (nie "archiwum_openmeteo" - to
    inny widok, przeszlosc nie przyszlosc) z NAJSWIEZSZEGO issue_date w
    CSV dla tej stacji (max() po stringu ISO - poprawnie sortuje sie
    leksykograficznie), posortowane po target_date rosnaco. Puste `days`
    (nie 404/500), jesli jeszcze nic nie zebrano - to normalny stan
    startowy, ten sam wzorzec co reszta endpointow w tym pliku."""
    st = _resolve_station(station)
    rows = [r for r in _read_rows(REAL_CSV, st.name) if r.get("source") == "prognoza"]
    if not rows:
        return {"station": st.name, "issue_date": None, "days": []}

    latest_issue = max(r["issue_date"] for r in rows if r.get("issue_date"))
    latest_rows = sorted(
        (r for r in rows if r.get("issue_date") == latest_issue),
        key=lambda r: r.get("target_date", ""),
    )
    days = [
        {
            "target_date": r.get("target_date"),
            "lead_days": r.get("lead_days"),
            "temp_min_c": r.get("temp_min_c"),
            "temp_max_c": r.get("temp_max_c"),
            "wind_direction_deg": r.get("wind_direction_deg"),
        }
        for r in latest_rows
    ]
    return {"station": st.name, "issue_date": latest_issue, "days": days}


@app.post("/api/collect")
def collect(station: str | None = None) -> dict:
    """Uruchamia faktyczne pobranie nowych danych (Open-Meteo) i dopisanie
    do REAL_CSV dla JEDNEJ wybranej stacji (`?station=`, domyslnie
    DEFAULT_STATION) - dokladnie ta sama logika co `python run_arctic.py`
    dla tej stacji (wspolna funkcja `collect()` w run_arctic.py), wywolana
    tutaj z ABSOLUTNA sciezka REAL_CSV (nie relatywna domyslna z
    run_arctic.py), zeby wynik NIE zalezal od katalogu roboczego procesu
    uvicorn.

    CELOWO tylko jedna stacja na klikniecie (nie wszystkie STATIONS na
    raz, w odroznieniu od run_arctic.main()/collect_all()) - przycisk w
    dashboardzie dziala na AKTUALNIE WYBRANEJ stacji z dropdowna, wiec
    klikniecie ma szybko i przewidywalnie odswiezyc TO, na co uzytkownik
    aktualnie patrzy, bez czekania na 7 zapytan do Open-Meteo naraz.
    Zebranie wszystkich stacji na raz nadal robi codzienne `run_arctic.py`.

    Powod istnienia tego przycisku: "Odswiez teraz" w dashboardzie tylko
    PONOWNIE CZYTA aktualny stan CSV z dysku - jesli nikt wczesniej nie
    uruchomil `run_arctic.py`/`run.bat`, na dysku faktycznie nie ma nic
    nowego do przeczytania, wiec przycisk "Odswiez" wyglada, jakby "nie
    ladowal danych", mimo ze dziala poprawnie (uczciwie zdiagnozowane po
    zgloszeniu tego jako bledu - to byla mylaca nazwa/workflow, nie blad
    w kodzie odswiezania). Ten endpoint pozwala zrobic OBIE rzeczy jednym
    kliknieciem w przegladarce, bez przelaczania sie do terminala/`run.bat`."""
    st = _resolve_station(station)
    return _collect_arctic_data(csv_path=str(REAL_CSV), station=st)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html_path = STATIC_DIR / "index.html"
    return html_path.read_text(encoding="utf-8")
