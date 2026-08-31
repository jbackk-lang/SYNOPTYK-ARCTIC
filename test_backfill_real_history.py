"""
test_backfill_real_history.py — testy na wstrzykniętych fetcherach (żadnego
żywego zapytania do Open-Meteo, ten sam wzorzec co test_previous_runs.py /
test_webapp.py). Sprawdzają dwie rzeczy: 1) że build_prognoza_groups()
poprawnie liczy issue_date z lead_days, 2) że backfill() faktycznie sprawia,
iż compute_lead_bias() ma co policzyć NATYCHMIAST (cel tego modułu - patrz
docstring backfill_real_history.py), bez czekania na kolejne dni
run_arctic.py.
"""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.bias import compute_lead_bias
from arctic_synoptyk.station import LONGYEARBYEN
from backfill_real_history import backfill, build_prognoza_groups

STATION = LONGYEARBYEN
STATION_NAME = STATION.name


def _hourly_payload(dates, lead_values):
    """Ten sam ksztalt co test_previous_runs.py::_hourly_payload - szczyt o
    12:00, reszta godzin nizsza, zeby max() mial co wybrac."""
    times = []
    fields = {f"temperature_2m_previous_day{n}": [] for n in lead_values}
    for d in dates:
        for hour in range(24):
            times.append(f"{d}T{hour:02d}:00")
            for n, day_values in lead_values.items():
                peak = day_values[d]
                fields[f"temperature_2m_previous_day{n}"].append(peak if hour == 12 else peak - 5)
    return {"hourly": {"time": times, **fields}}


def test_build_prognoza_groups_computes_issue_date_from_lead():
    by_lead = {
        1: {"2026-06-10": 5.0},
        3: {"2026-06-10": 4.0, "2026-06-12": 6.0},
    }
    groups = build_prognoza_groups(by_lead)

    assert set(groups.keys()) == {date(2026, 6, 7), date(2026, 6, 9)}

    # lead=3, target=06-10 -> issue=06-07 (jedyny wpis w tej grupie)
    assert groups[date(2026, 6, 7)] == [
        {"date": "2026-06-10", "temp_min_c": "", "temp_avg_c_approx": "",
         "temp_max_c": 4.0, "precip_mm": "", "pressure_hpa": "", "wind_kmh": ""}
    ]
    # lead=1, target=06-10 -> issue=06-09 ; lead=3, target=06-12 -> issue=06-09
    # (ta sama grupa, dwa rozne (lead, target) daja ten sam issue_date)
    assert groups[date(2026, 6, 9)] == [
        {"date": "2026-06-10", "temp_min_c": "", "temp_avg_c_approx": "",
         "temp_max_c": 5.0, "precip_mm": "", "pressure_hpa": "", "wind_kmh": ""},
        {"date": "2026-06-12", "temp_min_c": "", "temp_avg_c_approx": "",
         "temp_max_c": 6.0, "precip_mm": "", "pressure_hpa": "", "wind_kmh": ""},
    ]


def _archive_row(d, temp_max):
    return {
        "date": d, "temp_min_c": temp_max - 3, "temp_avg_c_approx": temp_max - 1.5,
        "temp_max_c": temp_max, "precip_mm": 0.0, "pressure_hpa": 1010.0, "wind_kmh": 5.0,
    }


def test_backfill_gives_compute_lead_bias_something_to_show_immediately():
    """Cel calego modulu: bez backfillu compute_lead_bias() jest pusty
    dopoki nie zbierze sie >= min_samples dni NA ZYWO (dni-tygodnie). Ten
    test sprawdza, ze jedno wywolanie backfill() z wystarczajaca proba
    historyczna daje wynik od razu."""
    dates = [f"2026-06-{d:02d}" for d in range(1, 8)]  # 7 dni
    by_lead = {1: {d: 5.0 for d in dates}}
    payload = _hourly_payload(dates, by_lead)
    archive_rows = [_archive_row(d, 6.0) for d in dates]

    def fake_previous_runs(station, past_days):
        return payload

    def fake_archive(station, past_days, exclude_trailing_days):
        return archive_rows

    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "test.csv")
        # keep_days=99999: fixture uzywa dat z czerwca 2026, dawno starszych
        # niz domyslna 30-dniowa retencja wzgledem PRAWDZIWEGO "dzisiaj" -
        # ten test sprawdza sam mechanizm backfillu, nie retencje (ktora ma
        # wlasny test nizej), wiec wylaczamy przycinanie.
        result = backfill(csv_path, STATION, past_days=7, max_lead_days=1, keep_days=99999,
                           _fetch_previous_runs=fake_previous_runs,
                           _fetch_archive=fake_archive)
        assert result["n_forecast_added"] == 7
        assert result["n_archive_added"] == 7

        bias = compute_lead_bias(csv_path, STATION_NAME, min_samples=5)
        assert 1 in bias
        assert bias[1]["n"] == 7
        assert bias[1]["bias"] == 1.0  # real(6.0) - forecast(5.0)


def test_backfill_is_idempotent_on_rerun():
    dates = [f"2026-06-{d:02d}" for d in range(1, 4)]
    by_lead = {1: {d: 5.0 for d in dates}}
    payload = _hourly_payload(dates, by_lead)
    archive_rows = [_archive_row(d, 6.0) for d in dates]

    def fake_previous_runs(station, past_days):
        return payload

    def fake_archive(station, past_days, exclude_trailing_days):
        return archive_rows

    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "test.csv")
        first = backfill(csv_path, STATION, past_days=3, max_lead_days=1, keep_days=99999,
                          _fetch_previous_runs=fake_previous_runs,
                          _fetch_archive=fake_archive)
        second = backfill(csv_path, STATION, past_days=3, max_lead_days=1, keep_days=99999,
                           _fetch_previous_runs=fake_previous_runs,
                           _fetch_archive=fake_archive)
        assert first["n_forecast_added"] == 3
        assert first["n_archive_added"] == 3
        assert second["n_forecast_added"] == 0
        assert second["n_archive_added"] == 0


def test_backfill_prunes_rows_older_than_keep_days():
    """Wiazanie z retention.py: backfill() z dawna historia (fixture z
    czerwca 2026, prawdziwe "dzisiaj" to sierpien/pozniej) i domyslnym
    keep_days=30 powinien od razu przyciac swiezo dopisane wiersze do
    pliku archiwalnego - dokladnie efekt, o ktory chodzilo w zgloszeniu
    ("ustaw max CSV na ostatnie 30 dni")."""
    dates = [f"2026-06-{d:02d}" for d in range(1, 4)]
    by_lead = {1: {d: 5.0 for d in dates}}
    payload = _hourly_payload(dates, by_lead)
    archive_rows = [_archive_row(d, 6.0) for d in dates]

    def fake_previous_runs(station, past_days):
        return payload

    def fake_archive(station, past_days, exclude_trailing_days):
        return archive_rows

    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "test.csv")
        result = backfill(csv_path, STATION, past_days=3, max_lead_days=1,
                           _fetch_previous_runs=fake_previous_runs,
                           _fetch_archive=fake_archive)
        # default keep_days=30; fixture dates sa relatywnie do prawdziwego
        # "dzisiaj" znacznie starsze niz 30 dni (ten plik testowy powstal
        # 2026-08-31) - wiec wszystko, co przed chwila dopisano, powinno
        # zostac natychmiast przeniesione do archiwum.
        assert result["n_pruned"] == result["n_forecast_added"] + result["n_archive_added"]
        assert result["n_pruned"] > 0
        assert not os.path.exists(csv_path) or open(csv_path).read().count("\n") <= 1
