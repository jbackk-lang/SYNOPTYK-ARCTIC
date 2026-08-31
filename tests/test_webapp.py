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
# Domyslna stacja bez ?station= (dodane 2026-08-31: Hornsund/Polska stala
# sie domyslna zamiast Longyearbyen, na wyrazna prosbe uzytkownika - patrz
# HISTORIA_BUDOWY.md). Testy PONIZEJ, ktore testuja "jakas stacja, wszystko
# jedno ktora" jawnie doklejaja `?station={STATION}` zamiast polegac na
# tym, co akurat jest domyslne - zeby nie rozjezdzaly sie przy kolejnej
# zmianie domyslnej stacji. Testy, ktorych PRZEDMIOTEM jest sama wartosc
# domyslna, uzywaja tej stalej wprost.
DEFAULT_STATION = "Hornsund_Polska_Stacja_Polarna"


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
            assert body["station"] == DEFAULT_STATION
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
            body = client.get(f"/api/status?station={STATION}").json()
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
            body = client.get(f"/api/real_bias?station={STATION}").json()
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
            body = client.get(f"/api/real_bias?station={STATION}").json()
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
            body = client.get(f"/api/latest_readings?station={STATION}").json()
            assert body["n_total"] == 1
            assert len(body["rows"]) == 1
            row = body["rows"][0]
            assert row["source"] == "prognoza"
            assert row["target_date"] == "2026-08-27"
            assert float(row["temp_max_c"]) == 3.8
            # a real_bias na tych samych danych jest pusty - potwierdza ze to
            # dwa rozne widoki tego samego CSV, nie duplikat tej samej logiki
            rb = client.get(f"/api/real_bias?station={STATION}").json()
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
            body = client.get(f"/api/latest_readings?limit=3&station={STATION}").json()
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


def test_index_page_shows_precip_and_wind_columns_in_readings_table():
    """Regression: tabela 'Surowe odczyty' pokazywala tylko temp_max i
    cisnienie, mimo ze precip_mm/wind_kmh sa juz w /api/latest_readings -
    zgloszenie uzytkownika ('nie ma wiatru... ani opadow')."""
    client = TestClient(app_module.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "opad mm" in r.text
    assert "wiatr km/h" in r.text
    assert "row.precip_mm" in r.text
    assert "row.wind_kmh" in r.text


def test_index_page_shows_wind_direction_arrow():
    """Zgloszenie: 'nie ma wiatru kierunku' + 'strzaleczka gruba, tak jak w
    zwyklym synoptyku' - ten sam zestaw 8 strzalek/logika co
    Synoptyk-v2.0 (gui_app.py::_WIND_ARROWS/_wind_arrow), wyrenderowana
    pogrubiona (klasa .wind-arrow)."""
    client = TestClient(app_module.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "kier." in r.text
    assert "windArrow" in r.text
    assert "↑" in r.text and "↗" in r.text and "↖" in r.text  # sam zestaw co Krakow
    assert ".wind-arrow" in r.text


def test_vendored_chartjs_is_served():
    client = TestClient(app_module.app)
    r = client.get("/static/vendor/chart.umd.js")
    assert r.status_code == 200
    assert b"Chart.js" in r.content
    assert len(r.content) > 100_000


def test_collect_endpoint_calls_shared_collect_with_absolute_real_csv():
    """POST /api/collect musi wywolywac run_arctic.collect() (ta sama funkcja
    co CLI/run.bat) z ABSOLUTNA sciezka REAL_CSV i wybrana stacja (tu: jawnie
    ?station= - patrz stala STATION - zeby test nie zalezal od tego, ktora
    stacja akurat jest domyslna), i zwracac jej wynik bez zmian - patrz
    docstring endpointu w webapp/app.py (dlaczego to osobny przycisk od
    "Odswiez teraz"). Monkeypatch na app_module._collect_arctic_data, zeby
    test NIE robil zywego zapytania do Open-Meteo."""
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
            r = client.post(f"/api/collect?station={STATION}")
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


# ── Wiele stacji (dodane 2026-08-31) ────────────────────────────────────

HORNSUND_STATION = DEFAULT_STATION  # ta sama stacja - Hornsund jest teraz domyslna


def test_stations_endpoint_lists_full_registry():
    """GET /api/stations - lista dla dropdowna w dashboardzie, patrz
    'Wiele stacji' w docstringu webapp/app.py. `default` to Hornsund
    (Polska Stacja Polarna) - zmienione z Longyearbyen na wyrazna prosbe
    uzytkownika ('ustaw polska jako domyslna'), patrz HISTORIA_BUDOWY.md.
    `north`/`south` to to samo co `stations`, tylko pogrupowane po
    polkuli (patrz ArcticStation.hemisphere) - dashboard buduje z nich
    dwa optgroup bez wlasnej logiki grupowania."""
    client = TestClient(app_module.app)
    r = client.get("/api/stations")
    assert r.status_code == 200
    body = r.json()
    assert body["default"] == DEFAULT_STATION
    names = {s["name"] for s in body["stations"]}
    assert STATION in names
    assert HORNSUND_STATION in names
    assert len(body["stations"]) == 10
    north_names = {s["name"] for s in body["north"]}
    south_names = {s["name"] for s in body["south"]}
    assert len(north_names) == 6
    assert len(south_names) == 4
    assert north_names | south_names == names
    assert north_names & south_names == set()
    assert all(s["hemisphere"] == "N" for s in body["north"])
    assert all(s["hemisphere"] == "S" for s in body["south"])


def test_status_filters_by_station_param():
    """?station=<konkretna stacja> ma zwrocic dane TEJ stacji, niezaleznie
    od tego, co jest domyslne - wiersze zapisane pod inna nazwa stacji nie
    powinny sie tam wcale pojawic (to samo filtrowanie po kolumnie
    'station', ktore _read_rows() robilo od poczatku). Dodatkowo:
    brak ?station= ma trafic w DEFAULT_STATION (Hornsund), nie w
    Longyearbyen - to jest wlasnie ta zmiana z 2026-08-31."""
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-27", 5.0)],
                         issue_date=date(2026, 8, 27), source="prognoza")
        append_snapshot(real_csv, DEFAULT_STATION, [_forecast_row("2026-08-27", -2.0)],
                         issue_date=date(2026, 8, 27), source="prognoza")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            r_default = client.get("/api/status")
            r_longyearbyen = client.get(f"/api/status?station={STATION}")
            assert r_default.json()["station"] == DEFAULT_STATION
            assert r_default.json()["n_rows_real"] == 1
            assert r_longyearbyen.json()["station"] == STATION
            assert r_longyearbyen.json()["n_rows_real"] == 1
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_latest_readings_filters_by_station_param():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-27", 5.0)],
                         issue_date=date(2026, 8, 27), source="prognoza")
        append_snapshot(real_csv, HORNSUND_STATION, [_forecast_row("2026-08-27", -2.0)],
                         issue_date=date(2026, 8, 27), source="prognoza")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            r = client.get(f"/api/latest_readings?station={HORNSUND_STATION}")
            body = r.json()
            assert body["n_total"] == 1
            assert body["rows"][0]["station"] == HORNSUND_STATION
            assert body["rows"][0]["temp_max_c"] == "-2.0"
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_unknown_station_returns_404_not_silent_fallback():
    """Ten sam duch co test_no_silent_default_for_missing_station w
    test_station.py: literowka w ?station= ma dac jawny blad, nie cicho
    spasc na Longyearbyen (co ukrywaloby, ze uzytkownik/front wyslal zla
    nazwe)."""
    client = TestClient(app_module.app)
    for path in ("/api/status", "/api/real_bias", "/api/latest_readings"):
        r = client.get(f"{path}?station=Nieistniejaca_Stacja")
        assert r.status_code == 404
    r = client.post("/api/collect?station=Nieistniejaca_Stacja")
    assert r.status_code == 404


# ── Prognoza 7 dni (dodane 2026-08-31) ──────────────────────────────────

def test_forecast_outlook_empty_when_no_data():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            r = client.get(f"/api/forecast_outlook?station={STATION}")
            assert r.status_code == 200
            body = r.json()
            assert body["issue_date"] is None
            assert body["days"] == []
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_forecast_outlook_returns_only_latest_issue_date_sorted_by_target_date():
    """Rdzen endpointu: wybiera TYLKO najswiezszy issue_date (nie miesza
    starszych prognoz z roznych dni zbierania) i sortuje po target_date
    rosnaco (dzien 0 -> +N), niezaleznie od kolejnosci zapisu w CSV."""
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        # Starsza prognoza (issue_date 2026-08-30) - NIE powinna sie pojawic.
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-31", 1.0)],
                         issue_date=date(2026, 8, 30), source="prognoza")
        # Najnowsza prognoza (issue_date 2026-08-31), zapisana w kolejnosci
        # NIE rosnacej po target_date - endpoint ma i tak posortowac.
        append_snapshot(real_csv, STATION, [_forecast_row("2026-09-01", 5.0)],
                         issue_date=date(2026, 8, 31), source="prognoza")
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-31", 3.0)],
                         issue_date=date(2026, 8, 31), source="prognoza")
        # Wiersz archiwum z tym samym (pozniejszym) issue_date - NIE jest
        # "prognoza", nie powinien wplynac na wynik.
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-25", -1.0)],
                         issue_date=date(2026, 8, 31), source="archiwum_openmeteo")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get(f"/api/forecast_outlook?station={STATION}").json()
            assert body["issue_date"] == "2026-08-31"
            assert [d["target_date"] for d in body["days"]] == ["2026-08-31", "2026-09-01"]
            assert body["days"][0]["temp_max_c"] == "3.0"
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_forecast_outlook_filters_by_station_param():
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        append_snapshot(real_csv, STATION, [_forecast_row("2026-08-31", 5.0)],
                         issue_date=date(2026, 8, 31), source="prognoza")
        append_snapshot(real_csv, DEFAULT_STATION, [_forecast_row("2026-08-31", -8.0)],
                         issue_date=date(2026, 8, 31), source="prognoza")
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)
        try:
            client = TestClient(app_module.app)
            body = client.get(f"/api/forecast_outlook?station={DEFAULT_STATION}").json()
            assert len(body["days"]) == 1
            assert body["days"][0]["temp_max_c"] == "-8.0"
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo


def test_forecast_outlook_unknown_station_404():
    client = TestClient(app_module.app)
    r = client.get("/api/forecast_outlook?station=Nieistniejaca_Stacja")
    assert r.status_code == 404


def test_index_page_has_forecast_outlook_panel():
    """Regression: sam JS/HTML panelu 'Prognoza 7 dni' ma byc w
    wyrenderowanej stronie (svg, tabela, funkcja renderujaca) - ten sam
    plytki wzorzec co inne testy sprawdzajace obecnosc panelu w index.html."""
    client = TestClient(app_module.app)
    r = client.get("/")
    assert r.status_code == 200
    assert "Prognoza 7 dni" in r.text
    assert "outlook-chart" in r.text
    assert "renderForecastOutlook" in r.text
    assert "/api/forecast_outlook" in r.text


def test_collect_endpoint_uses_requested_station_not_always_longyearbyen():
    """POST /api/collect?station=<X> ma wywolac collect() z ArcticStation
    odpowiadajacym X, nie zawsze LONGYEARBYEN - to byla poprzednia,
    jednostacyjna wersja tego endpointu."""
    with tempfile.TemporaryDirectory() as d:
        real_csv, demo_csv = _client_with_real_csv(d)
        old_real, old_demo = app_module.REAL_CSV, app_module.DEMO_CSV
        old_collect = app_module._collect_arctic_data
        app_module.REAL_CSV, app_module.DEMO_CSV = Path(real_csv), Path(demo_csv)

        captured = {}

        def fake_collect(csv_path, station):
            captured["station"] = station
            return {
                "date": "2026-08-31", "station": station.name,
                "n_forecast_added": 1, "n_archive_added": 0,
                "forecast_error": None, "archive_error": None,
                "bias": {}, "raw_counts": None,
            }

        app_module._collect_arctic_data = fake_collect
        try:
            client = TestClient(app_module.app)
            r = client.post(f"/api/collect?station={HORNSUND_STATION}")
            assert r.status_code == 200
            assert captured["station"].name == HORNSUND_STATION
            assert r.json()["station"] == HORNSUND_STATION
        finally:
            app_module.REAL_CSV, app_module.DEMO_CSV = old_real, old_demo
            app_module._collect_arctic_data = old_collect
