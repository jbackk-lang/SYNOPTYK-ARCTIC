import csv
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.snapshots import append_snapshot, FIELDNAMES


def _sample_records():
    return [
        {"date": "2026-08-26", "temp_min_c": 0.5, "temp_avg_c_approx": 2.15,
         "temp_max_c": 3.8, "precip_mm": 0.0, "wind_kmh": 14.5, "pressure_hpa": 1023.9},
        {"date": "2026-08-27", "temp_min_c": 0.0, "temp_avg_c_approx": 3.1,
         "temp_max_c": 6.2, "precip_mm": 0.0, "wind_kmh": 6.8, "pressure_hpa": 1024.9},
    ]


def test_append_creates_file_with_header():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic_snapshots.csv")
        n = append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                             issue_date=date(2026, 8, 26), source="prognoza")
        assert n == 2
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == FIELDNAMES
            rows = list(reader)
        assert len(rows) == 2


def test_lead_days_computed_correctly():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic_snapshots.csv")
        append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                         issue_date=date(2026, 8, 26), source="prognoza")
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["lead_days"] == "0"   # 2026-08-26, issue=2026-08-26
        assert rows[1]["lead_days"] == "1"   # 2026-08-27


def test_append_twice_accumulates_not_overwrites():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic_snapshots.csv")
        append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                         issue_date=date(2026, 8, 26), source="prognoza")
        append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                         issue_date=date(2026, 8, 27), source="prognoza")
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 4


def test_source_field_recorded():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic_snapshots.csv")
        append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                         issue_date=date(2026, 8, 26), source="archiwum_openmeteo")
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert all(r["source"] == "archiwum_openmeteo" for r in rows)
