"""
bias.py — identyczna logika co `synoptyk-v2.0/forecaster/bias_correction.py`,
przeniesiona na schemat CSV z `snapshots.py`.

Zamierzone podobieństwo: to ten sam algorytm (bias = rzeczywistość -
prognoza, per lead_days, tylko gdy >= min_samples par), sprawdzony już na
1236 parach dla Krakowa - tu tylko zmieniona nazwa kolumny prognozy
(`temp_max_c` zamiast `avg_temp_c`, bo Open-Meteo `daily=` nie daje
prawdziwej średniej - patrz fetch.py) i źródła "rzeczywistości"
(`archiwum_openmeteo` zamiast `IMGW_real_*`/`OpenMeteo_real_dailymax`).

Z JEDNYM pobraniem (2026-08-26) ten moduł zwróci pusty słownik - i tak
powinno być (min_samples=5 domyślnie). To oczekiwane, nie błąd: dokładnie
tak samo Krakow nie miał żadnej działającej korekty, dopóki nie zebrało
się kilka tygodni logów (patrz README).
"""
from __future__ import annotations

import csv
from collections import defaultdict


def _load_pairs(csv_path: str, station: str, forecast_col: str = "temp_max_c") -> list[dict]:
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return []

    rows = [r for r in rows if r.get("station") == station]
    fc = [r for r in rows if r.get("source") == "prognoza"]
    real = [r for r in rows if r.get("source") == "archiwum_openmeteo"]

    real_by_date: dict[str, float] = {}
    for r in real:
        v = r.get(forecast_col)
        if v not in (None, ""):
            real_by_date[r["target_date"]] = float(v)

    pairs = []
    for r in fc:
        real_val = real_by_date.get(r["target_date"])
        fc_val = r.get(forecast_col)
        lead = r.get("lead_days")
        if real_val is None or fc_val in (None, "") or lead in (None, ""):
            continue
        pairs.append({
            "lead_days": int(float(lead)),
            "forecast": float(fc_val),
            "real": real_val,
        })
    return pairs


def compute_lead_bias(
    csv_path: str,
    station: str,
    min_samples: int = 5,
    forecast_col: str = "temp_max_c",
) -> dict[int, dict]:
    """Zwraca {lead_days: {"bias": ..., "mae": ..., "n": ...}} TYLKO dla
    lead_days z >= min_samples sparowanymi obserwacjami - brak wpisu =
    brak korekty (za mało danych), nie zero."""
    pairs = _load_pairs(csv_path, station, forecast_col=forecast_col)
    if not pairs:
        return {}

    by_lead: dict[int, list[dict]] = defaultdict(list)
    for p in pairs:
        by_lead[p["lead_days"]].append(p)

    result: dict[int, dict] = {}
    for lead, group in by_lead.items():
        n = len(group)
        if n < min_samples:
            continue
        errors = [g["real"] - g["forecast"] for g in group]
        result[lead] = {
            "bias": round(sum(errors) / n, 3),
            "mae": round(sum(abs(e) for e in errors) / n, 3),
            "n": n,
        }
    return result
