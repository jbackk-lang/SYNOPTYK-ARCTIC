"""
test_retention.py — testy arctic_synoptyk/retention.py na izolowanych,
tymczasowych CSV (nigdy nie dotyka prawdziwego arctic_forecast_snapshots.csv).
"""
import csv
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.retention import (
    FIELDNAMES, DEFAULT_KEEP_DAYS, archive_path_for, prune_old_rows,
)
from arctic_synoptyk.snapshots import FIELDNAMES as SNAPSHOTS_FIELDNAMES

TODAY = date(2026, 8, 31)


def test_fieldnames_match_snapshots_module():
    """retention.FIELDNAMES jest zduplikowane (nie importowane) z
    snapshots.py, zeby uniknac cyklu importow - ten test pilnuje, zeby obie
    listy sie nie rozjechaly, gdyby ktos zmienil schemat CSV w jednym
    miejscu, a zapomnial o drugim."""
    assert FIELDNAMES == SNAPSHOTS_FIELDNAMES


def _row(target_date, source="prognoza", station="Longyearbyen_Svalbard"):
    return {
        "station": station, "target_date": target_date, "issue_date": target_date,
        "lead_days": "0", "temp_min_c": "1", "temp_avg_c_approx": "2",
        "temp_max_c": "3", "precip_mm": "0", "pressure_hpa": "1010",
        "wind_kmh": "5", "source": source,
    }


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_prune_moves_old_rows_to_archive_and_keeps_recent():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "snap.csv")
        _write_csv(csv_path, [
            _row("2026-07-01"),   # 61 dni przed TODAY -> stare
            _row("2026-08-15"),   # 16 dni przed TODAY -> w oknie 30 dni
            _row("2026-08-31"),   # dzisiaj -> w oknie
        ])
        n = prune_old_rows(csv_path, keep_days=30, _today=TODAY)
        assert n == 1

        hot = _read_csv(csv_path)
        assert {r["target_date"] for r in hot} == {"2026-08-15", "2026-08-31"}

        archive = _read_csv(archive_path_for(csv_path))
        assert {r["target_date"] for r in archive} == {"2026-07-01"}


def test_prune_noop_when_nothing_old():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "snap.csv")
        _write_csv(csv_path, [_row("2026-08-30"), _row("2026-08-31")])
        n = prune_old_rows(csv_path, keep_days=30, _today=TODAY)
        assert n == 0
        assert not os.path.exists(archive_path_for(csv_path))  # zaden zapis, jesli nic do wyniesienia
        assert len(_read_csv(csv_path)) == 2


def test_prune_missing_file_is_noop():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "does_not_exist.csv")
        assert prune_old_rows(csv_path, keep_days=30, _today=TODAY) == 0


def test_prune_keeps_rows_with_unparseable_target_date():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "snap.csv")
        rows = [_row("2026-07-01"), _row("")]
        rows[1]["target_date"] = "not-a-date"
        _write_csv(csv_path, rows)
        n = prune_old_rows(csv_path, keep_days=30, _today=TODAY)
        assert n == 1  # tylko wiersz z parsowalna, stara data
        hot = _read_csv(csv_path)
        assert {r["target_date"] for r in hot} == {"not-a-date"}


def test_prune_appends_to_existing_archive_without_duplicating_header():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "snap.csv")
        archive_path = archive_path_for(csv_path)

        _write_csv(csv_path, [_row("2026-07-01"), _row("2026-08-31")])
        prune_old_rows(csv_path, keep_days=30, _today=TODAY)
        assert len(_read_csv(archive_path)) == 1

        # kolejny dzien: nowy stary wiersz dochodzi do TEGO SAMEGO archiwum,
        # nie nadpisuje go
        _write_csv(csv_path, _read_csv(csv_path) + [_row("2026-07-02")])
        prune_old_rows(csv_path, keep_days=30, _today=TODAY)
        archive_rows = _read_csv(archive_path)
        assert {r["target_date"] for r in archive_rows} == {"2026-07-01", "2026-07-02"}
        # naglowek wystapil tylko raz (DictReader by inaczej zgubil/nie
        # sparsowal poprawnie - ale sprawdzmy tez wprost liczbe linii)
        with open(archive_path, encoding="utf-8") as f:
            header_lines = [ln for ln in f if ln.startswith("station,")]
        assert len(header_lines) == 1


def test_default_keep_days_is_30():
    """Wartosc uzgodniona z uzytkownikiem: 30 dni w zupelnosci wystarcza do
    policzenia bias/MAE (min_samples=5 per lead_days, max lead=7 - patrz
    docstring modulu)."""
    assert DEFAULT_KEEP_DAYS == 30
