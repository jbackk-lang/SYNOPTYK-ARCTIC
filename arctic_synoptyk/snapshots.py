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
    "precip_mm", "pressure_hpa", "wind_kmh", "source",
]


def _lead_days(target_date_str: str, issue_date: date) -> int:
    td = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    return (td - issue_date).days


def append_snapshot(
    csv_path: str,
    station_name: str,
    records: Iterable[dict[str, Any]],
    issue_date: date,
    source: str,
) -> int:
    """Dopisuje wiersze do CSV (tworzy plik z nagłówkiem, jeśli nie istnieje).
    Zwraca liczbę dopisanych wierszy.

    `records` to wynik `fetch.fetch_forecast()`/`fetch_archive()` (lista
    słowników z kluczem 'date' + wartości pogodowe) - `lead_days` liczone
    tutaj, nie w fetch.py, żeby jedno pobranie dało się zalogować z różnym
    `issue_date` w testach bez ponownego odpytywania API."""
    file_exists = os.path.isfile(csv_path)
    rows_written = 0
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        for rec in records:
            writer.writerow({
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
                "source": source,
            })
            rows_written += 1
    return rows_written
