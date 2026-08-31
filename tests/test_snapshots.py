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


def test_append_same_day_twice_is_idempotent():
    """Rdzen bugu znalezionego na realnym uzyciu: uruchomienie run_arctic.py
    kilka razy tego samego dnia (ten sam issue_date) NIE powinno dopisywac
    tych samych wierszy ponownie - inaczej n w compute_lead_bias() rosnie
    sztucznie (wygladalo na 5 zebranych dni, a to byl jeden dzien
    zduplikowany 5x)."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic_snapshots.csv")
        n1 = append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                              issue_date=date(2026, 8, 26), source="prognoza")
        n2 = append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                              issue_date=date(2026, 8, 26), source="prognoza")
        assert n1 == 2
        assert n2 == 0, "drugie wywolanie z tym samym issue_date/source nie powinno nic dopisac"
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2


def test_append_fills_missing_wind_direction_on_existing_key():
    """Rdzen naprawy z 2026-08-31: wiersz zapisany PRZED dodaniem
    wind_direction_deg do fetch.py ma to pole puste na stale, bo klucz
    idempotentnosci sie nie zmienia w ciagu tego samego dnia. Ponowne
    wywolanie append_snapshot() z tym samym kluczem, ale rekordem, ktory
    TERAZ ma wind_direction_deg, ma dopisac te wartosc do istniejacego
    wiersza - bez tego kolumna 'kier.' zostaje pusta az do jutra."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic_snapshots.csv")
        old_rec = [{"date": "2026-08-31", "temp_min_c": 0.0, "temp_avg_c_approx": 1.0,
                     "temp_max_c": 2.0, "precip_mm": 0.0, "wind_kmh": 5.0,
                     "pressure_hpa": 1020.0}]  # brak wind_direction_deg w ogole
        n1 = append_snapshot(csv_path, "Longyearbyen_Svalbard", old_rec,
                              issue_date=date(2026, 8, 31), source="prognoza")
        assert n1 == 1
        new_rec = [{"date": "2026-08-31", "temp_min_c": 0.0, "temp_avg_c_approx": 1.0,
                     "temp_max_c": 2.0, "precip_mm": 0.0, "wind_kmh": 5.0,
                     "pressure_hpa": 1020.0, "wind_direction_deg": 245.0}]
        n2 = append_snapshot(csv_path, "Longyearbyen_Svalbard", new_rec,
                              issue_date=date(2026, 8, 31), source="prognoza")
        assert n2 == 0, "to nie jest nowy wiersz - sam klucz juz istnial"
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1, "uzupelnienie pola nie ma dublowac wiersza"
        assert rows[0]["wind_direction_deg"] == "245.0"


def test_append_never_overwrites_existing_wind_direction():
    """Uzupelnianie dziala tylko w jedna strone: nigdy nie nadpisuje juz
    zapisanej realnej wartosci nowa (nawet jesli sie roznia) - to by
    zamazywalo, co Open-Meteo faktycznie zwrocilo w danym pobraniu."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic_snapshots.csv")
        rec_a = [{"date": "2026-08-31", "temp_min_c": 0.0, "temp_avg_c_approx": 1.0,
                   "temp_max_c": 2.0, "precip_mm": 0.0, "wind_kmh": 5.0,
                   "pressure_hpa": 1020.0, "wind_direction_deg": 100.0}]
        append_snapshot(csv_path, "Longyearbyen_Svalbard", rec_a,
                         issue_date=date(2026, 8, 31), source="prognoza")
        rec_b = [{"date": "2026-08-31", "temp_min_c": 0.0, "temp_avg_c_approx": 1.0,
                   "temp_max_c": 2.0, "precip_mm": 0.0, "wind_kmh": 5.0,
                   "pressure_hpa": 1020.0, "wind_direction_deg": 300.0}]
        append_snapshot(csv_path, "Longyearbyen_Svalbard", rec_b,
                         issue_date=date(2026, 8, 31), source="prognoza")
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        assert rows[0]["wind_direction_deg"] == "100.0"


def test_append_different_issue_date_still_accumulates():
    """Idempotencja jest po kluczu (station, target_date, issue_date,
    source) - INNY issue_date (kolejny dzien) to legalnie nowy wiersz,
    nie duplikat."""
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic_snapshots.csv")
        append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                         issue_date=date(2026, 8, 26), source="prognoza")
        n2 = append_snapshot(csv_path, "Longyearbyen_Svalbard", _sample_records(),
                              issue_date=date(2026, 8, 27), source="prognoza")
        assert n2 == 2
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 4
