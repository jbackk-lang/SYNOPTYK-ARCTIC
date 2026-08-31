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

Zweryfikowane na prawdziwej odpowiedzi API 2026-08-27 (`backtest_real.py`,
90 dni, Longyearbyen) — parsowanie zadziałało bez poprawek, zgodnie z
udokumentowanym kształtem odpowiedzi (godzinowe pola
`temperature_2m_previous_dayN`, N=1..7). Sandbox deweloperski nadal ma
zablokowany dostęp do `previous-runs-api.open-meteo.com` (ten sam problem
co dla `archive-api.open-meteo.com`, patrz README) — testy jednostkowe
(`test_previous_runs.py`) używają ręcznie zbudowanego payloadu, nie
zapisanej realnej odpowiedzi (nie zapisano jej jako fixture, bo
uruchomienie było poza tym środowiskiem).

ROZSZERZENIE (2026-08-31): opad i wiatr dołączone tym samym wzorcem co
temperatura — `precipitation_previous_dayN`/`wind_speed_10m_previous_dayN`,
te same nazwy godzinowych zmiennych co zwykły `hourly=` endpoint Open-Meteo
(`precipitation`, `wind_speed_10m`), z dopiskiem `_previous_dayN`, przez
analogię do już potwierdzonego `temperature_2m_previous_dayN`.
**NIEZWERYFIKOWANE na żywej odpowiedzi API** — tylko temperatura miała
realny test 2026-08-27. Kod rzuca KeyError jawnie, jeśli któregoś pola
zabraknie (patrz `_aggregate_by_lead()` niżej), więc pierwsze uruchomienie
`backfill_real_history.py` po tej zmianie samo to zweryfikuje; jeśli
KeyError wyskoczy, zgłosić dokładną nazwę brakującego pola — to sygnał,
że rzeczywisty kształt odpowiedzi różni się od tego założenia, nie błąd
do zignorowania.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import requests

from .station import ArcticStation

PREVIOUS_RUNS_BASE_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
MAX_LEAD_DAYS = 7

# Domyślne godzinowe zmienne pobierane przez fetch_previous_runs() - te same
# nazwy co w zwykłym hourly= endpoincie Open-Meteo (NIE nazwy dobowe z
# fetch.py, tam już zagregowane po stronie API - tu agregujemy sami, patrz
# AGGREGATIONS niżej).
DEFAULT_HOURLY_VARS = ("temperature_2m", "precipitation", "wind_speed_10m")

# Recepta agregacji dobowej: {kolumna_CSV: (godzinowa_zmienna_OpenMeteo, funkcja_agregujaca)}.
# Te same definicje co fetch.py (max dla temp/wiatru - dobowe maksimum;
# suma dla opadu), żeby backfillowane wiersze dały się porównać 1:1 z
# wierszami z run_arctic.py/fetch_archive().
AGGREGATIONS: dict[str, tuple[str, Callable]] = {
    "temp_max_c": ("temperature_2m", max),
    "precip_mm": ("precipitation", sum),
    "wind_kmh": ("wind_speed_10m", max),
}


def fetch_previous_runs(
    station: ArcticStation,
    past_days: int = 90,
    max_lead_days: int = MAX_LEAD_DAYS,
    timeout: float = 30.0,
    hourly_vars: tuple[str, ...] = DEFAULT_HOURLY_VARS,
) -> dict[str, Any]:
    """Pobiera surową odpowiedź JSON (godzinową) z Previous Runs API dla
    lead_days 1..max_lead_days, dla każdej zmiennej w `hourly_vars`. Zwraca
    surowy payload — parsowanie w `daily_max_by_lead()`/
    `daily_aggregates_by_lead()`, żeby dało się testować na zapisanej
    odpowiedzi bez ponownego zapytania (ten sam wzorzec co `fetch.py`)."""
    fields = [f"{var}_previous_day{n}" for var in hourly_vars for n in range(1, max_lead_days + 1)]
    url = (
        f"{PREVIOUS_RUNS_BASE_URL}?latitude={station.lat}&longitude={station.lon}"
        f"&hourly={','.join(fields)}&past_days={past_days}&forecast_days=1&timezone=UTC"
    )
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _aggregate_by_lead(
    payload: dict[str, Any],
    hourly_var: str,
    agg_fn: Callable,
    max_lead_days: int,
) -> dict[int, dict[str, float]]:
    """Agreguje JEDNĄ godzinową zmienną (`{hourly_var}_previous_dayN`) do
    {lead_days: {data_iso: wartosc_dobowa}} funkcją `agg_fn` (np. max,
    sum). Wspólny rdzeń dla `daily_max_by_lead()` i
    `daily_aggregates_by_lead()`.

    Rzuca KeyError jawnie, jeśli brakuje oczekiwanego pola dla danego
    lead_days (patrz `fetch.py._parse_daily_response` — ten sam wzorzec:
    nie ukrywać zmiany kształtu odpowiedzi API)."""
    hourly = payload["hourly"]
    times = hourly["time"]

    result: dict[int, dict[str, float]] = {}
    for n in range(1, max_lead_days + 1):
        key = f"{hourly_var}_previous_day{n}"
        if key not in hourly:
            raise KeyError(f"brak oczekiwanego pola '{key}' w odpowiedzi Previous Runs API")
        values = hourly[key]
        by_date: dict[str, list[float]] = defaultdict(list)
        for t, v in zip(times, values):
            if v is None:
                continue
            date_str = t.split("T")[0]
            by_date[date_str].append(v)
        result[n] = {d: agg_fn(vals) for d, vals in by_date.items() if vals}

    return result


def daily_max_by_lead(
    payload: dict[str, Any],
    max_lead_days: int = MAX_LEAD_DAYS,
) -> dict[int, dict[str, float]]:
    """Zamienia godzinową odpowiedź Previous Runs API na
    {lead_days: {data_iso: prognozowany_temp_max_c}} — agregując 24
    punkty/dzień do maksimum (ta sama definicja co `temperature_2m_max`
    w `fetch.py`/Archive API, żeby dało się porównać 1:1). Tylko
    temperatura — do backtestu wielu zmiennych naraz patrz
    `daily_aggregates_by_lead()`.

    Rzuca KeyError jawnie, jeśli brakuje oczekiwanego pola dla danego
    lead_days."""
    return _aggregate_by_lead(payload, "temperature_2m", max, max_lead_days)


def daily_aggregates_by_lead(
    payload: dict[str, Any],
    aggregations: dict[str, tuple[str, Callable]] = AGGREGATIONS,
    max_lead_days: int = MAX_LEAD_DAYS,
) -> dict[int, dict[str, dict[str, float]]]:
    """Jak `daily_max_by_lead()`, ale dla wielu zmiennych naraz (domyślnie
    temperatura + opad + wiatr, patrz `AGGREGATIONS`) —
    {lead_days: {data_iso: {kolumna_CSV: wartość}}}, gotowe do
    `backfill_real_history.build_prognoza_groups()`.

    Jeśli dla danego dnia brakuje wartości dla którejś zmiennej (np. luka w
    danych źródłowych), ta jedna kolumna zostaje pominięta w słowniku dla
    tego dnia — reszta zmiennych i tak trafia do CSV (`_forecast_record()`
    w `backfill_real_history.py` wypełnia brakujące klucze pustym stringiem,
    tak jak każdy inny niekompletny wiersz w tym CSV)."""
    per_column: dict[str, dict[int, dict[str, float]]] = {
        output_key: _aggregate_by_lead(payload, hourly_var, agg_fn, max_lead_days)
        for output_key, (hourly_var, agg_fn) in aggregations.items()
    }

    result: dict[int, dict[str, dict[str, float]]] = {
        n: defaultdict(dict) for n in range(1, max_lead_days + 1)
    }
    for output_key, by_lead in per_column.items():
        for lead, by_date in by_lead.items():
            for d, value in by_date.items():
                result[lead][d][output_key] = value

    return {lead: dict(by_date) for lead, by_date in result.items()}


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
