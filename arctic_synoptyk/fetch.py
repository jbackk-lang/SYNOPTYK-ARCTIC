"""
fetch.py — pobieranie prognozy/archiwum z Open-Meteo dla stacji arktycznej.

Używa endpointu DOBOWEGO (`daily=`), nie godzinowego (`hourly=`) jak
Synoptyk-v2.0 dla Krakowa. To świadoma różnica, nie przeoczenie:

- Krakow: pobiera godzinowe dane, sam agreguje do dobowych (`_daily_stats`
  w gui_app.py) - dzięki temu ma prawdziwą średnią dobową (`temp_avg`)
  liczoną z 24 punktów, i może zasilić filtr falkowy/TIMDR gęstszym
  sygnałem.
- Tu: Open-Meteo sam agreguje dobowo po swojej stronie. Prostsze, mniej
  kodu, ale NIE MA prawdziwej średniej dobowej - tylko `temperature_2m_max`
  i `temperature_2m_min`. `avg_temp_c` w tym module jest WYLICZANE jako
  (max+min)/2 - to przybliżenie, nie ta sama wielkość co Krakowa `avg`
  (systematycznie się różnią dla asymetrycznych przebiegów dobowych -
  patrz README, sekcja "Różnice metodologiczne vs Synoptyk-v2.0").
  Filtr falkowy/TIMDR na sygnale dobowym (7-10 punktów) też będzie miał
  dużo mniej do analizy niż na godzinowym - to nie jest tu jeszcze
  wpięte (patrz README, "Czego brakuje").
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import requests

from .station import ArcticStation

_DAILY_FIELDS = (
    "temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "wind_speed_10m_max,pressure_msl_mean,wind_direction_10m_dominant"
)

FORECAST_BASE_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"


def _parse_daily_response(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Zamienia surowy JSON Open-Meteo (klucz 'daily', kolumnowo) na listę
    wierszy (po jednym słowniku na dzień) - łatwiejsze do logowania w CSV
    i do testowania niż surowa struktura kolumnowa.

    Rzuca KeyError, jeśli brakuje 'daily' albo 'time' - jawnie, zamiast
    cicho zwracać pustą listę (żeby zmiana kształtu odpowiedzi API nie
    przeszła niezauważona, patrz timdr-signal-framework §4 o cichych
    awariach schematu). WYJĄTEK: `wind_direction_10m_dominant` jest
    opcjonalne (`.get()`, None jeśli brak) - dodane 2026-08-31, PO
    zapisaniu fixture'ów w tests/fixtures/*.json (patrz test_fetch.py), więc
    te dwa realne, zapisane payloady legalnie go nie mają. Dla NOWYCH
    zapytań pole jest zawsze w `_DAILY_FIELDS`, więc powinno być obecne -
    ale traktujemy jego ewentualny brak jako brak danych (None), nie jako
    zmianę kształtu odpowiedzi wartą wywalenia się (w odróżnieniu od
    pozostałych pięciu pól, zweryfikowanych na żywym payloadzie i
    wymaganych na sztywno)."""
    daily = payload["daily"]
    dates = daily["time"]
    wind_dir_list = daily.get("wind_direction_10m_dominant")

    rows = []
    for i, d in enumerate(dates):
        t_max = daily["temperature_2m_max"][i]
        t_min = daily["temperature_2m_min"][i]
        avg = None
        if t_max is not None and t_min is not None:
            avg = round((t_max + t_min) / 2, 2)
        rows.append({
            "date": d,
            "temp_min_c": t_min,
            "temp_avg_c_approx": avg,  # patrz zastrzezenie w docstringu modulu
            "temp_max_c": t_max,
            "precip_mm": daily["precipitation_sum"][i],
            "wind_kmh": daily["wind_speed_10m_max"][i],
            "pressure_hpa": daily["pressure_msl_mean"][i],
            "wind_direction_deg": wind_dir_list[i] if wind_dir_list is not None else None,
        })
    return rows


def fetch_forecast(station: ArcticStation, forecast_days: int = 7, timeout: float = 20.0) -> list[dict[str, Any]]:
    """Pobiera prognozę dobową (do 16 dni, ograniczone tu do 7 domyślnie -
    dokładnie tyle, ile zweryfikowano ręcznie 2026-08-26)."""
    url = (
        f"{FORECAST_BASE_URL}?latitude={station.lat}&longitude={station.lon}"
        f"&daily={_DAILY_FIELDS}&forecast_days={forecast_days}&timezone=UTC"
    )
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return _parse_daily_response(r.json())


def fetch_archive(
    station: ArcticStation,
    past_days: int = 10,
    timeout: float = 20.0,
    exclude_trailing_days: int = 2,
    _today: date | None = None,
) -> list[dict[str, Any]]:
    """Pobiera zarejestrowaną historię (past_days wstecz od dziś).

    `exclude_trailing_days` (domyślnie 2) odcina najświeższe dni z odpowiedzi
    przed zwróceniem - Open-Meteo Archive API zwraca dane aż do dziś, ale dla
    ostatnich ~1-2 dni to jeszcze nie jest sfinalizowana reanaliza, tylko
    dane praktycznie identyczne z modelem prognozy (ten sam problem
    udokumentowany dla Krakowa w README: "Open-Meteo Archive API ma
    opóźnienie ~1-2 dni"). Znalezione empirycznie tutaj: pierwsze prawdziwe
    porównanie prognoza-vs-archiwum dla lead_days=0 dało bias=0.00, MAE=0.00
    dokładnie dlatego, że oba źródła zwracały tę samą, jeszcze
    niesfinalizowaną liczbę - nie dlatego, że prognoza była idealna. Bez
    tego obcięcia `compute_lead_bias()` liczyłby korektę na parach, które
    nie są niezależnym porównaniem prognoza/rzeczywistość.

    `_today` - tylko do testów (żeby nie zależeć od zegara systemowego)."""
    url = (
        f"{ARCHIVE_BASE_URL}?latitude={station.lat}&longitude={station.lon}"
        f"&daily={_DAILY_FIELDS}&past_days={past_days}&timezone=UTC"
    )
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    rows = _parse_daily_response(r.json())

    if exclude_trailing_days <= 0:
        return rows

    today = _today if _today is not None else date.today()
    cutoff = today - timedelta(days=exclude_trailing_days - 1)
    return [
        row for row in rows
        if datetime.strptime(row["date"], "%Y-%m-%d").date() < cutoff
    ]
