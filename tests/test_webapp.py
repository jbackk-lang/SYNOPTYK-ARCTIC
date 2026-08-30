"""
test_webapp.py — testy endpointow FastAPI (webapp/app.py) na IZOLOWANYCH,
tymczasowych CSV (nigdy nie dotykaja prawdziwego arctic_forecast_snapshots.csv
ani demo_synthetic_arctic_snapshots.csv w repo) - monkeypatch modulowych
stalych REAL_CSV/DEMO_CSV, dokladnie po to zaprojektowanych w app.py.
"""
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from arctic_synoptyk.snapshots import append_snapshot
from webapp import app as app_module

STATION = "Longyearbyen_Svalbard"
DEMO_STATION = "Longyearbyen_Svalbard_DEMO"


def _forecast_row(target_date, temp_max):
    return {"date": target_date, "temp_min_c": temp_max - 3, "temp_avg_c_approx": temp_max - 1.5,
            "temp_max_c": temp_max, "precip_mm": 0.0, "wind_kmh": 10.0, "pressure_hpa": 1010.0}


def _client_with_real_csv(tmp_dir, rows_writer=None):
    """Podmienia app_module.REAL_CSV/DEMO_CSV na pliki w tmp_dir na czas
    testu i zwraca TestClient. Odtwarza sciezki po tescie (finally w teście
    wywolujacym, nie tutaj - patrz uzycie ponizej z try/finally)."""
    real_csv = os.path.join(tmp_dir, "real.csv")
    demo_csv = os.path.join(tmp_dir, "demo.csv")
    if rows_writer:
        rows_writer(real_csv, demo_csv)
    return real_csv, demo_csv


def test_status_no_data_yet():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            r = client.get("/api/status")
            assert r.status_code == 200
            body = r.json()
            assert body["station"] == STATION
            assert body["n_rows_real"] == 0
            assert body["last_issue_date"] is None
            assert body["staleness"] is None
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_status_reports_staleness_from_last_issue_date():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        old_dt = datetime.now(timezone.utc) - timedelta(days=10)
        append_snapshot(real_csv, STATION, [_forecast_row(old_dt.date().isoformat(), 3.0)],
                         issue_date=old_dt.date(), source="prognoza")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get("/api/status").json()
            assert body["n_rows_real"] == 1
            assert body["last_issue_date"] == old_dt.date().isoformat()
            # 10 dni wieku -> pasmo STALE (3-14 dni), patrz offline.py
            assert body["staleness"] == "stale"
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_real_bias_empty_when_below_min_samples():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-27", 6.2)],
                         issue_date=date(2026, 8, 26), source="prognoza")
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-27", 7.0)],
                         issue_date=date(2026, 8, 27), source="archiwum_openmeteo")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get("/api/real_bias").json()
            assert body["official"] == {}, "n=1 < min_samples=5, wiec zero oficjalnych wynikow"
            assert body["raw_counts"].get("1") == 1 or body["raw_counts"].get(1) == 1
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_real_bias_populates_after_enough_samples():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        for day in range(21, 27):
            target = f"2026-08-{day:02d}"
            append_snapshot(real_csv, STATION, [_forecast_row(target, 5.0)],
                             issue_date=date(2026, 8, day - 1), source="prognoza")
            append_snapshot(real_csv, STATION, [_forecast_row(target, 6.0)],
                             issue_date=date(2026, 8, day), source="archiwum_openmeteo")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get("/api/real_bias").json()
            assert "1" in body["official"]
            assert body["official"]["1"]["n"] == 6
            assert body["official"]["1"]["bias"] == 1.0
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_demo_bias_missing_file_returns_explicit_error():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)  # demo_csv nie istnieje
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get("/api/demo_bias").json()
            assert "error" in body
            assert body["bias"] == {}
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_demo_bias_always_carries_disclaimer_when_present():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        for day in range(1, 7):
            target = f"2026-08-{day:02d}"
            append_snapshot(demo_csv, DEMO_STATION, [_forecast_row(target, 5.0)],
                             issue_date=date(2026, 8, day - 1) if day > 1 else date(2026, 7, 31),
                             source="prognoza")
            append_snapshot(demo_csv, DEMO_STATION, [_forecast_row(target, 6.0)],
                             issue_date=date(2026, 8, day), source="archiwum_openmeteo")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get("/api/demo_bias").json()
            assert "SYNTETYCZNE" in body["disclaimer"]
            assert body["station"] == DEMO_STATION
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_latest_readings_empty_when_no_data():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get("/api/latest_readings").json()
            assert body["rows"] == []
            assert body["n_total"] == 0
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_latest_readings_shows_rows_even_when_unpaired():
    """To jest dokladnie przypadek, ktory /api/real_bias celowo ukrywa
    (n < min_samples albo brak pokrycia target_date przez archiwum) - tu
    surowy wiersz ma byc widoczny mimo to, zeby dalo sie sprawdzic ze
    kolektor cos zapisuje."""
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-27", 3.8)],
                         issue_date=date(2026, 8, 27), source="prognoza")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get("/api/latest_readings").json()
            assert body["n_total"] == 1
            assert len(body["rows"]) == 1
            row = body["rows"][0]
            assert row["source"] == "prognoza"
            assert row["target_date"] == "2026-08-27"
            assert float(row["temp_max_c"]) == 3.8
            # a real_bias na tych samych danych jest pusty - potwierdza ze to
            # dwa rozne widoki tego samego CSV, nie duplikat tej samej logiki
            rb = client.get("/api/real_bias").json()
            assert rb["official"] == {}
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_latest_readings_sorted_newest_first_and_respects_limit():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        for day in range(20, 28):
            append_snapshot(real_csv, STATION, [_forecast_row(f"2026-08-{day:02d}", 5.0)],
                             issue_date=date(2026, 8, day), source="prognoza")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get("/api/latest_readings?limit=3").json()
            assert body["n_total"] == 8
            assert len(body["rows"]) == 3
            assert body["rows"][0]["issue_date"] == "2026-08-27"
            assert body["rows"][-1]["issue_date"] == "2026-08-25"
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_index_page_serves_html():
    client = TestClient(app_module.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "SYNOPTYK-ARCTIC" in r.text
    assert "text/html" in r.headers["content-type"]


def test_index_page_does_not_reference_external_cdn():
    """
    Regression test: index.html used to load Chart.js from
    cdnjs.cloudflare.com. On a locked-down corporate network that request
    silently failed, `Chart` was never defined, and the "Odswiez teraz"
    button appeared to do nothing (loadAll() died partway through on
    `new Chart(...)`, before rendering the rest of the panels). Chart.js is
    now vendored locally under webapp/static/vendor/ - the page must not
    reference any external script host.
    """
    client = TestClient(app_module.app)
    r = client.get("/")
    assert r.status_code == 200
    assert 'src="http' not in r.text
    assert '<script src="/static/vendor/chart.umd.js"></script>' in r.text


def test_vendored_chartjs_is_served():
    client = TestClient(app_module.app)
    r = client.get("/static/vendor/chart.umd.js")
    assert r.status_code == 200
    assert b"Chart.js" in r.content
    assert len(r.content) > 100_000


def test_collect_endpoint_calls_shared_collect_with_absolute_real_csv():
    """POST /api/collect musi wywolywac run_arctic.collect() (ta sama funkcja
    co CLI/run.bat) z ABSOLUTNA sciezka REAL_CSV i stacja LONGYEARBYEN, i
    zwracac jej wynik bez zmian - patrz docstring endpointu w webapp/app.py
    (dlaczego to osobny przycisk od "Odswiez teraz"). Monkeypatch na
    app_module._collect_arctic_data, zeby test NIE robil zywego zapytania do
    Open-Meteo."""
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        old_collect = app_module._collect_arctic_data
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)

        captured = {}

        def fake_collect(csv_path, station):
            captured["csv_path"] = csv_path
            captured["station"] = station
            return {
                "date": "2026-08-30",
                "station": station.name,
                "n_forecast_added": 3,
                "n_archive_added": 2,
                "forecast_error": None,
                "archive_error": None,
                "bias": {},
                "raw_counts": None,
            }

        app_module._collect_arctic_data = fake_collect
        try:
            client = TestClient(app_module.app)
            r = client.post("/api/collect")
            assert r.status_code == 200
            body = r.json()
            assert body["n_forecast_added"] == 3
            assert body["n_archive_added"] == 2
            assert captured["csv_path"] == str(Path(real_csv))
            assert captured["station"].name == STATION
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo
            app_module._collect_arctic_data = old_collect


def test_collect_endpoint_passes_through_fetch_errors():
    """Jesli fetch_forecast/fetch_archive zawiodly (np. brak sieci), collect()
    zwraca to w forecast_error/archive_error zamiast rzucac wyjatek (patrz
    run_arctic.collect) - endpoint musi to przekazac 1:1, nie polykac ani nie
    zamieniac w 500."""
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        old_collect = app_module._collect_arctic_data
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)

        def fake_collect(csv_path, station):
            return {
                "date": "2026-08-30",
                "station": station.name,
                "n_forecast_added": 0,
                "n_archive_added": 0,
                "forecast_error": "Connection timeout",
                "archive_error": None,
                "bias": {},
                "raw_counts": None,
            }

        app_module._collect_arctic_data = fake_collect
        try:
            client = TestClient(app_module.app)
            r = client.post("/api/collect")
            assert r.status_code == 200
            body = r.json()
            assert body["forecast_error"] == "Connection timeout"
            assert body["n_forecast_added"] == 0
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo
            app_module._collect_arctic_data = old_collect
