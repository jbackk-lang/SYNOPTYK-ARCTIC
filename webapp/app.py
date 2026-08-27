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
- GET  /api/latest_readings — SUROWE, NIESPAROWANE wiersze z REAL_CSV (i
                         "prognoza", i "archiwum_openmeteo"), posortowane
                         od najnowszych. Cel: dać widoczność, że kolektor w
                         ogóle działa i zapisuje realne liczby, zanim
                         uzbiera się >= min_samples par potrzebnych do
                         /api/real_bias - bez tego endpointu jedyny sposób
                         sprawdzenia "czy coś się zbiera" to zajrzenie do
                         CSV ręcznie na dysku.

Ścieżki do plików CSV są modułowymi stałymi (REAL_CSV/DEMO_CSV) właśnie po
to, żeby testy mogły je podmienić (monkeypatch) na izolowane pliki
tymczasowe - appka nigdy nie pisze do CSV, tylko czyta, więc to bezpieczne.
"""
from __future__ import annotations

import csv as _csv
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from arctic_synoptyk.bias import compute_lead_bias
from arctic_synoptyk.offline import classify_staleness
from arctic_synoptyk.station import LONGYEARBYEN

BASE_DIR = Path(__file__).resolve().parent.parent
REAL_CSV = BASE_DIR / "arctic_forecast_snapshots.csv"
DEMO_CSV = BASE_DIR / "demo_synthetic_arctic_snapshots.csv"
STATION = LONGYEARBYEN.name
DEMO_STATION = "Longyearbyen_Svalbard_DEMO"
MIN_SAMPLES = 5

app = FastAPI(title="SYNOPTYK-ARCTIC Dashboard")


def _read_rows(csv_path: Path, station: str) -> list[dict]:
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    return [r for r in rows if r.get("station") == station]


@app.get("/api/status")
def status() -> dict:
    rows = _read_rows(REAL_CSV, STATION)
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
        "station": STATION,
        "lat": LONGYEARBYEN.lat,
        "lon": LONGYEARBYEN.lon,
        "n_rows_real": len(rows),
        "n_days_collected": len(issue_dates),
        "last_issue_date": last_issue_date,
        "staleness": staleness,
        "staleness_label_pl": staleness_label,
        "min_samples_required": MIN_SAMPLES,
    }


@app.get("/api/real_bias")
def real_bias() -> dict:
    official = compute_lead_bias(str(REAL_CSV), STATION, min_samples=MIN_SAMPLES)
    raw = compute_lead_bias(str(REAL_CSV), STATION, min_samples=1)
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
def latest_readings(limit: int = 20) -> dict:
    """Surowe wiersze z REAL_CSV (obu źródeł - "prognoza" i
    "archiwum_openmeteo"), posortowane malejąco po (issue_date, target_date).

    Celowo NIE wymaga sparowania prognoza<->rzeczywistość ani min_samples -
    to jest widok "czy pipeline żyje", nie widok trafności. Jeśli tu coś
    się pokazuje, kolektor faktycznie pisze dane; brak wpisów dla
    lead_days=0 w /api/real_bias to wtedy potwierdzone kwestia progu/
    opóźnienia archiwum, a nie tego, że nic się nie zbiera."""
    rows = _read_rows(REAL_CSV, STATION)
    rows_sorted = sorted(
        rows,
        key=lambda r: (r.get("issue_date", ""), r.get("target_date", "")),
        reverse=True,
    )
    return {"rows": rows_sorted[:limit], "n_total": len(rows)}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")
