"""
previous_runs.py — realny backtest trafności prognozy Open-Meteo na dużej
próbce historycznej, przez Previous Runs API
(previous-runs-api.open-meteo.com), które archiwizuje prognozy sprzed lat
na STAŁYCH lead_days (1-7) — dokładnie po to zaprojektowane przez
Open-Meteo do oceny skuteczności prognoz w czasie
(https://open-meteo.com/en/docs/previous-runs-api).

Różni się od `run_arctic.py` (codzienne zbieranie na żywo, tygodnie do
wyniku): to pobiera JEDNYM zapytaniem np. 90 dni PRAWDZIWEJ historii
prognoz vs rzeczywistość, więc wynik jest natychmiastowy — ale nadal dla
konkretnego, historycznego okna (nie dowodzi nic o przyszłych prognozach,
które `run_arctic.py` musi nadal zbierać na bieżąco).

WAŻNE — nie zweryfikowane jeszcze na prawdziwej odpowiedzi API. Sandbox ma
zablokowany dostęp do `previous-runs-api.open-meteo.com` (ten sam problem
co dla `archive-api.open-meteo.com`, patrz README) — parsowanie poniżej
jest oparte WYŁĄCZNIE na udokumentowanym kształcie odpowiedzi (godzinowe
pola `temperature_2m_previous_dayN`, N=1..7), nie na realnej próbce.
Pierwsze uruchomienie `backtest_real.py` na laptopie jest testem tej
hipotezy, nie gotowym wynikiem — jeśli kształt odpowiedzi okaże się inny
(np. inne nazwy pól, brak `hourly`), zgłosić: to będzie wymagało poprawki
parsera, nie oznacza błędu w metodzie.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import requests

from .station import ArcticStation

PREVIOUS_RUNS_BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
MAX_LEAD_DAYS = 7


def fetch_previous_runs(
    station: ArcticStation,
    past_days: int = 90,
    max_lead_days: int = MAX_LEAD_DAYS,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Pobiera surową odpowiedź JSON (godzinową) z Previous Runs API dla
    lead_days 1..max_lead_days. Zwraca surowy payload — parsowanie w
    `daily_max_by_lead()`, żeby dało się testować na zapisanej odpowiedzi
    bez ponownego zapytania (ten sam wzorzec co `fetch.py`)."""
    fields = [f"temperature_2m_previous_day{n}" for n in range(1, max_lead_days + 1)]
    url = (
        f"{PREVIOUS_RUNS_BASE_URL}?latitude={station.lat}&longitude={station.lon}"
        f"&hourly={','.join(fields)}&past_days={past_days}&forecast_days=1&timezone=UTC"
    )
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def daily_max_by_lead(
    payload: dict[str, Any],
    max_lead_days: int = MAX_LEAD_DAYS,
) -> dict[int, dict[str, float]]:
    """Zamienia godzinową odpowiedź Previous Runs API na
    {lead_days: {data_iso: prognozowany_temp_max_c}} — agregując 24
    punkty/dzień do maksimum (ta sama definicja co `temperature_2m_max`
    w `fetch.py`/Archive API, żeby dało się porównać 1:1).

    Rzuca KeyError jawnie, jeśli brakuje oczekiwanego pola dla danego
    lead_days (patrz `fetch.py._parse_daily_response` — ten sam wzorzec:
    nie ukrywać zmiany kształtu odpowiedzi API)."""
    hourly = payload["hourly"]
    times = hourly["time"]

    result: dict[int, dict[str, float]] = {}
    for n in range(1, max_lead_days + 1):
        key = f"temperature_2m_previous_day{n}"
        if key not in hourly:
            raise KeyError(f"brak oczekiwanego pola '{key}' w odpowiedzi Previous Runs API")
        values = hourly[key]
        by_date: dict[str, list[float]] = defaultdict(list)
        for t, v in zip(times, values):
            if v is None:
                continue
            date_str = t.split("T")[0]
            by_date[date_str].append(v)
        result[n] = {d: max(vals) for d, vals in by_date.items() if vals}

    return result


def backtest_bias(
    by_lead: dict[int, dict[str, float]],
    real_by_date: dict[str, float],
    min_samples: int = 5,
) -> dict[int, dict[str, float]]:
    """Liczy bias/MAE per lead_days z wyjścia `daily_max_by_lead()` wobec
    rzeczywistych wartości (`real_by_date`, np. z `fetch.fetch_archive()`).
    Ta sama definicja co `bias.compute_lead_bias()`: bias = rzeczywistość
    − prognoza, tylko dla lead_days z >= min_samples sparowanymi dniami."""
    out: dict[int, dict[str, float]] = {}
    for lead, forecasts in by_lead.items():
        pairs = [
            (forecasts[d], real_by_date[d])
            for d in forecasts
            if d in real_by_date
        ]
        n = len(pairs)
        if n < min_samples:
            continue
        errors = [real - fc for fc, real in pairs]
        out[lead] = {
            "bias": round(sum(errors) / n, 3),
            "mae": round(sum(abs(e) for e in errors) / n, 3),
            "n": n,
        }
    return out
