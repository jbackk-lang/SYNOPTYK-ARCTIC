import csv
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.snapshots import append_snapshot
from arctic_synoptyk.bias import compute_lead_bias, _load_pairs

STATION = "Longyearbyen_Svalbard"


def _forecast_row(target_date, temp_max):
    return {"date": target_date, "temp_min_c": temp_max - 3, "temp_avg_c_approx": temp_max - 1.5,
            "temp_max_c": temp_max, "precip_mm": 0.0, "wind_kmh": 10.0, "pressure_hpa": 1010.0}


def test_empty_csv_returns_empty_dict():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "does_not_exist.csv")
        assert compute_lead_bias(csv_path, STATION) == {}


def test_below_min_samples_returns_no_entry_for_that_lead():
    """Rdzen tego etapu: z jednym pobraniem (tak jak realnie mamy teraz dla
    Longyearbyen, 2026-08-26) NIE powinno byc zadnej korekty - to nie blad,
    to uczciwy status 'za malo danych' (patrz README)."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic.csv")
        # jedna prognoza + jeden pasujacy "rzeczywisty" wpis - n=1, ponizej min_samples=5
        append_snapshot(csv_path, STATION, [_forecast_row("2026-08-27", 6.2)],
                         issue_date=date(2026, 8, 26), source="prognoza")
        append_snapshot(csv_path, STATION, [_forecast_row("2026-08-27", 7.0)],
                         issue_date=date(2026, 8, 27), source="archiwum_openmeteo")
        result = compute_lead_bias(csv_path, STATION, min_samples=5)
        assert result == {}, "z n=1 korekta nie powinna sie wlaczyc (min_samples=5 domyslnie)"


def test_reaches_min_samples_after_enough_paired_days():
    """Symulacja tego, co sie stanie po ~2 tygodniach regularnego logowania
    (analogicznie do Krakowa) - PO zebraniu >=5 par, korekta faktycznie
    dziala i liczy bias/MAE poprawnie."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic.csv")
        # 6 dni z lead_days=1, prognoza systematycznie o 1.0 nizsza niz "rzeczywistosc"
        for day in range(21, 27):
            target = f"2026-08-{day:02d}"
            issue = f"2026-08-{day-1:02d}"
            append_snapshot(csv_path, STATION, [_forecast_row(target, 5.0)],
                             issue_date=date(2026, 8, day - 1), source="prognoza")
            append_snapshot(csv_path, STATION, [_forecast_row(target, 6.0)],
                             issue_date=date(2026, 8, day), source="archiwum_openmeteo")

        result = compute_lead_bias(csv_path, STATION, min_samples=5)
        assert 1 in result
        assert result[1]["n"] == 6
        assert result[1]["bias"] == 1.0   # rzeczywistosc (6.0) - prognoza (5.0)
        assert result[1]["mae"] == 1.0


def test_different_station_names_not_mixed():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic.csv")
        append_snapshot(csv_path, "Inna_Stacja", [_forecast_row("2026-08-27", 6.2)],
                         issue_date=date(2026, 8, 26), source="prognoza")
        pairs = _load_pairs(csv_path, STATION)
        assert pairs == []
