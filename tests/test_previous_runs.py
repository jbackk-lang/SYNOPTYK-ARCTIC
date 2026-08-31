"""
test_previous_runs.py — testy na RECZNIE ZBUDOWANYM payloadzie zgodnym z
UDOKUMENTOWANYM ksztaltem odpowiedzi Previous Runs API (nie z prawdziwej
odpowiedzi - sandbox ma zablokowany dostep do previous-runs-api.open-meteo.com,
patrz previous_runs.py). Jesli po pierwszym realnym uruchomieniu
backtest_real.py okaze sie, ze ksztalt jest inny, te testy tez trzeba
bedzie poprawic - traktowac je jako test hipotezy o formacie, nie jako
dowod, ze parser dziala na prawdziwych danych.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from arctic_synoptyk.previous_runs import daily_max_by_lead, daily_aggregates_by_lead, backtest_bias


def _hourly_payload(dates, lead_values):
    """Buduje payload w ksztalcie: 24 godziny/dzien, z jedna szczytowa
    wartoscia (informacyjnie 'w poludnie') na dzien per lead, reszta godzin
    nizsza - zeby max() mial co wybrac."""
    times = []
    fields = {f"temperature_2m_previous_day{n}": [] for n in lead_values}
    for d in dates:
        for hour in range(24):
            times.append(f"{d}T{hour:02d}:00")
            for n, day_values in lead_values.items():
                peak = day_values[d]
                # szczyt o 12:00, reszta godzin nizsza wartosc
                fields[f"temperature_2m_previous_day{n}"].append(peak if hour == 12 else peak - 5)
    return {"hourly": {"time": times, **fields}}


def test_daily_max_by_lead_picks_peak_per_day():
    dates = ["2026-06-01", "2026-06-02"]
    lead_values = {
        1: {"2026-06-01": 5.0, "2026-06-02": 6.0},
        2: {"2026-06-01": 4.0, "2026-06-02": 5.5},
    }
    payload = _hourly_payload(dates, lead_values)
    result = daily_max_by_lead(payload, max_lead_days=2)
    assert result[1] == {"2026-06-01": 5.0, "2026-06-02": 6.0}
    assert result[2] == {"2026-06-01": 4.0, "2026-06-02": 5.5}


def test_daily_max_by_lead_raises_keyerror_on_missing_field():
    payload = {"hourly": {"time": ["2026-06-01T00:00"], "temperature_2m_previous_day1": [5.0]}}
    with pytest.raises(KeyError):
        daily_max_by_lead(payload, max_lead_days=2)  # brakuje _previous_day2


def test_daily_max_by_lead_skips_none_values():
    payload = {
        "hourly": {
            "time": ["2026-06-01T00:00", "2026-06-01T12:00"],
            "temperature_2m_previous_day1": [None, 7.0],
        }
    }
    result = daily_max_by_lead(payload, max_lead_days=1)
    assert result[1] == {"2026-06-01": 7.0}


def test_backtest_bias_matches_compute_lead_bias_semantics():
    """bias = rzeczywistosc - prognoza, tylko gdy n >= min_samples - ta sama
    semantyka co bias.compute_lead_bias(), zeby wyniki byly bezposrednio
    porownywalne."""
    by_lead = {
        1: {f"2026-06-{d:02d}": 5.0 for d in range(1, 7)},  # 6 dni
    }
    real_by_date = {f"2026-06-{d:02d}": 6.0 for d in range(1, 7)}
    result = backtest_bias(by_lead, real_by_date, min_samples=5)
    assert result[1]["n"] == 6
    assert result[1]["bias"] == 1.0
    assert result[1]["mae"] == 1.0


def test_backtest_bias_empty_below_min_samples():
    by_lead = {1: {"2026-06-01": 5.0, "2026-06-02": 5.0}}
    real_by_date = {"2026-06-01": 6.0, "2026-06-02": 6.0}
    result = backtest_bias(by_lead, real_by_date, min_samples=5)
    assert result == {}


def test_backtest_bias_only_pairs_dates_present_in_both():
    by_lead = {1: {f"2026-06-{d:02d}": 5.0 for d in range(1, 8)}}  # 7 dni prognozy
    real_by_date = {f"2026-06-{d:02d}": 6.0 for d in range(1, 6)}  # tylko 5 dni rzeczywistosci
    result = backtest_bias(by_lead, real_by_date, min_samples=5)
    assert result[1]["n"] == 5


def _multi_var_payload(dates, lead, temp_by_date, precip_by_date, wind_by_date):
    """Payload z trzema zmiennymi naraz (temp/opad/wiatr) dla JEDNEGO
    lead_days - szczyt o 12:00 dla temp/wiatru (zeby max() mial co
    wybrac), cala wartosc opadu w godzinie 0 (zeby sum() dala dokladnie
    precip_by_date[d])."""
    times = []
    temp_field, precip_field, wind_field = [], [], []
    for d in dates:
        for hour in range(24):
            times.append(f"{d}T{hour:02d}:00")
            temp_field.append(temp_by_date[d] if hour == 12 else temp_by_date[d] - 5)
            precip_field.append(precip_by_date[d] if hour == 0 else 0.0)
            wind_field.append(wind_by_date[d] if hour == 12 else wind_by_date[d] - 2)
    return {"hourly": {
        "time": times,
        f"temperature_2m_previous_day{lead}": temp_field,
        f"precipitation_previous_day{lead}": precip_field,
        f"wind_speed_10m_previous_day{lead}": wind_field,
    }}


def test_daily_aggregates_by_lead_combines_temp_precip_wind():
    dates = ["2026-06-01", "2026-06-02"]
    payload = _multi_var_payload(
        dates, lead=1,
        temp_by_date={"2026-06-01": 5.0, "2026-06-02": 6.0},
        precip_by_date={"2026-06-01": 1.2, "2026-06-02": 0.0},
        wind_by_date={"2026-06-01": 10.0, "2026-06-02": 12.0},
    )
    result = daily_aggregates_by_lead(payload, max_lead_days=1)
    assert result[1]["2026-06-01"] == {"temp_max_c": 5.0, "precip_mm": 1.2, "wind_kmh": 10.0}
    assert result[1]["2026-06-02"] == {"temp_max_c": 6.0, "precip_mm": 0.0, "wind_kmh": 12.0}


def test_daily_aggregates_by_lead_raises_keyerror_on_missing_field():
    payload = {"hourly": {"time": ["2026-06-01T00:00"], "temperature_2m_previous_day1": [5.0]}}
    with pytest.raises(KeyError):
        daily_aggregates_by_lead(payload, max_lead_days=1)  # brakuje precipitation_/wind_speed_10m_previous_day1


def test_daily_max_by_lead_unaffected_by_extra_variables_in_payload():
    """fetch_previous_runs() domyslnie pyta o temp+opad+wiatr, ale
    backtest_real.py nadal uzywa TYLKO daily_max_by_lead() (temperatura) -
    dodatkowe pola w payloadzie nie powinny nic popsuc."""
    dates = ["2026-06-01"]
    payload = _multi_var_payload(
        dates, lead=1,
        temp_by_date={"2026-06-01": 5.0},
        precip_by_date={"2026-06-01": 1.2},
        wind_by_date={"2026-06-01": 10.0},
    )
    result = daily_max_by_lead(payload, max_lead_days=1)
    assert result == {1: {"2026-06-01": 5.0}}
