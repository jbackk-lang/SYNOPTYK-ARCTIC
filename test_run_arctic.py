"""
test_run_arctic.py — testy run_arctic.collect() na wstrzykniętych fetcherach
(_fetch_forecast/_fetch_archive), zaden zywy request do Open-Meteo. Skupione
na tym, co nie jest juz pokryte przez test_webapp.py (ktory testuje warstwe
HTTP wokol collect(), nie sama funkcje) - w tym wpiecie prune_old_rows()
(patrz "ustaw max CSV" w rozmowie z uzytkownikiem, retention.py).
"""
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.station import LONGYEARBYEN
from run_arctic import collect

STATION = LONGYEARBYEN


def _forecast_row(target_date, temp_max=5.0):
    return {"date": target_date, "temp_min_c": temp_max - 3, "temp_avg_c_approx": temp_max - 1.5,
            "temp_max_c": temp_max, "precip_mm": 0.0, "wind_kmh": 10.0, "pressure_hpa": 1010.0}


def test_collect_appends_forecast_and_archive_rows():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "snap.csv")
        today = date.today()

        def fake_forecast(station, forecast_days):
            return [_forecast_row((today + timedelta(days=i)).isoformat()) for i in range(forecast_days)]

        def fake_archive(station, past_days):
            return [_forecast_row((today - timedelta(days=i)).isoformat(), temp_max=6.0) for i in range(1, past_days + 1)]

        result = collect(csv_path, STATION, _fetch_forecast=fake_forecast, _fetch_archive=fake_archive)
        assert result["n_forecast_added"] == 7
        assert result["n_archive_added"] == 10
        assert result["forecast_error"] is None
        assert result["archive_error"] is None


def test_collect_survives_fetch_errors_without_touching_csv():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "snap.csv")

        def failing_forecast(station, forecast_days):
            raise RuntimeError("boom - no network")

        def failing_archive(station, past_days):
            raise RuntimeError("boom - no network")

        result = collect(csv_path, STATION, _fetch_forecast=failing_forecast, _fetch_archive=failing_archive)
        assert result["forecast_error"] == "boom - no network"
        assert result["archive_error"] == "boom - no network"
        assert result["n_forecast_added"] == 0
        assert result["n_archive_added"] == 0
        # append_snapshot() tworzy plik z samym naglowkiem nawet przy zero
        # rekordach (otwiera go w trybie "a" bezwarunkowo) - to zachowanie
        # sprzed tej zmiany, nie cos wprowadzonego przez retencje. Istotne
        # jest to, ze NIE MA zadnego wiersza z danymi.
        if os.path.exists(csv_path):
            with open(csv_path, encoding="utf-8") as f:
                assert len(f.readlines()) <= 1


def test_collect_prunes_rows_older_than_keep_days():
    """Zbieranie na zywo tez ma korzystac z retencji, nie tylko backfill -
    tu symulujemy archiwum siegajace dawno wstecz (past_days duze) i
    sprawdzamy, ze n_pruned > 0 przy malym keep_days."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "snap.csv")
        today = date.today()

        def fake_forecast(station, forecast_days):
            return [_forecast_row(today.isoformat())]

        def fake_archive(station, past_days):
            # jeden wiersz na tyle dni wstecz, ile domyslnie pyta collect()
            # (past_days=10) - wszystkie starsze niz keep_days=3 powinny
            # zostac przyciete
            return [_forecast_row((today - timedelta(days=i)).isoformat(), temp_max=6.0) for i in range(1, past_days + 1)]

        result = collect(csv_path, STATION, keep_days=3,
                          _fetch_forecast=fake_forecast, _fetch_archive=fake_archive)
        assert result["n_pruned"] > 0
        # wiersze starsze niz 3 dni wstecz (4..10 dni wstecz = 7 wierszy)
        # powinny zostac przeniesione, 1-3 dni wstecz + dzisiejsza prognoza zostaja
        assert result["n_pruned"] == 7
