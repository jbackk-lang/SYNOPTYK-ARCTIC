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


def test_index_page_serves_html():
    client = TestClient(app_module.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "SYNOPTYK-ARCTIC" in r.text
    assert "text/html" in r.headers["content-type"]
