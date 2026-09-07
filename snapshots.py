"""
snapshots.py — logowanie pobranych danych do CSV, w schemacie analogicznym
do `krakow_forecast_snapshots.csv` w Synoptyk-v2.0 (te same nazwy pojęć:
`issue_date`, `lead_days`, `source`), żeby dało się policzyć bias/MAE
dokładnie tą samą metodą co dla Krakowa (patrz `bias.py`).

Źródła (`source`):
- "prognoza" - wiersz z fetch_forecast() (przyszłość względem issue_date)
- "archiwum_openmeteo" - wiersz z fetch_archive() (przeszłość względem
  issue_date). UWAGA: to reanaliza/najlepsze dostępne dane Open-Meteo, NIE
  surowy odczyt z instrumentu stacji - dokładnie ten sam status co
  `OpenMeteo_real_dailymax` w Synoptyk-v2.0 (tam już używane jako proxy
  "rzeczywistości" do liczenia bias/MAE, patrz forecaster/bias_correction.py
  - to sprawdzony wzorzec, nie nowe założenie).

To repo NIE ma jeszcze prawdziwego odczytu z fizycznego czujnika stacji
arktycznej (nikt taki nie jest podłączony) - `archiwum_openmeteo` to
najlepsze dostępne przybliżenie "rzeczywistości", z tym samym zastrzeżeniem
co w Synoptyk-v2.0.
"""
from __future__ import annotations

import csv
import os
from datetime import date, datetime
from typing import Any, Iterable

FIELDNAMES = [
    "station", "target_date", "issue_date", "lead_days",
    "temp_min_c", "temp_avg_c_approx", "temp_max_c",
    "precip_mm", "pressure_hpa", "wind_kmh", "wind_direction_deg", "source",
]


def _lead_days(target_date_str: str, issue_date: date) -> int:
    td = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    return (td - issue_date).days


def _read_rows(csv_path: str) -> list[dict[str, str]]:
    if not os.path.isfile(csv_path):
        return []
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_snapshot(
    csv_path: str,
    station_name: str,
    records: Iterable[dict[str, Any]],
    issue_date: date,
    source: str,
) -> int:
    """Dopisuje wiersze do CSV (tworzy plik z nagłówkiem, jeśli nie istnieje).
    Zwraca liczbę FAKTYCZNIE dopisanych (nowych) wierszy (pomijając
    duplikaty) - patrz też "uzupelnianie brakujacych pol" nizej, to sie
    liczy osobno i NIE wchodzi do tego zwracanego `n`.

    `records` to wynik `fetch.fetch_forecast()`/`fetch_archive()` (lista
    słowników z kluczem 'date' + wartości pogodowe) - `lead_days` liczone
    tutaj, nie w fetch.py, żeby jedno pobranie dało się zalogować z różnym
    `issue_date` w testach bez ponownego odpytywania API.

    IDEMPOTENTNE po kluczu (station, target_date, issue_date, source):
    ponowne uruchomienie `run_arctic.py` tego samego dnia (ten sam
    `issue_date`) NIE dopisuje drugi raz tych samych wierszy. Bez tego
    kazde uruchomienie skryptu w ciagu dnia sztucznie zawyzalo `n` w
    `compute_lead_bias()` - wygladalo na przyrost danych, a w
    rzeczywistosci to byl ten sam, pojedynczy dzien zduplikowany
    (znaleziono to po tym, jak recznie uruchomiony `run_arctic.py`
    kilka razy jednego dnia dal n=5 dla lead_days=0 zamiast n=1).

    UZUPELNIANIE BRAKUJACYCH POL na juz istniejacym kluczu: gdy klucz juz
    jest w CSV, ale ma puste `wind_direction_deg` (np. wiersz zapisany
    2026-08-31 PRZED dodaniem tego pola do fetch.py w tym samym dniu -
    idempotentnosc po kluczu inaczej trwale zablokowalaby mu ta wartosc,
    dopoki nie zmieni sie `issue_date` jutro), a nowy `rec` faktycznie ma
    te wartosc - dopisujemy ja do istniejacego wiersza zamiast go pomijac
    w ciszy. Dotyczy tylko pol juz pustych (nigdy nie nadpisuje realnej
    wartosci nowa) i nie zmienia zwracanego `n` (to nie jest nowy wiersz)."""
    rows = _read_rows(csv_path)
    index = {
        (r["station"], r["target_date"], r["issue_date"], r["source"]): r
        for r in rows
    }
    rows_written = 0
    for rec in records:
        key = (station_name, rec["date"], issue_date.isoformat(), source)
        existing_row = index.get(key)
        if existing_row is not None:
            new_dir = rec.get("wind_direction_deg")
            if not existing_row.get("wind_direction_deg") and new_dir not in (None, ""):
                existing_row["wind_direction_deg"] = new_dir
            continue
        new_row = {
            "station": station_name,
            "target_date": rec["date"],
            "issue_date": issue_date.isoformat(),
            "lead_days": _lead_days(rec["date"], issue_date),
            "temp_min_c": rec["temp_min_c"],
            "temp_avg_c_approx": rec["temp_avg_c_approx"],
            "temp_max_c": rec["temp_max_c"],
            "precip_mm": rec["precip_mm"],
            "pressure_hpa": rec["pressure_hpa"],
            "wind_kmh": rec["wind_kmh"],
            # .get(): dodane 2026-08-31, PO tym jak demo_synthetic_fill.py
            # i backfill_real_history.py zaczely wywolywac append_snapshot()
            # z rekordami bez tego klucza w ogole (demo go nie generuje,
            # Previous Runs API nie dostarcza kierunku w bezpieczny,
            # niekolowy sposob - patrz backfill_real_history.py) - bez
            # .get() te wywolania rzucalyby KeyError zamiast po prostu
            # zostawic puste pole, jak kazdy inny brakujacy parametr w
            # tym CSV.
            "wind_direction_deg": rec.get("wind_direction_deg", ""),
            "source": source,
        }
        rows.append(new_row)
        index[key] = new_row
        rows_written += 1
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return rows_written
