"""
test_fetch.py — testy na PRAWDZIWYCH odpowiedziach API (fixtures w
tests/fixtures/*.json, pobrane 2026-08-26 z laptopa uzytkownika - sandbox
Claude ma zablokowany dostep do api.open-meteo.com, patrz README).

Nie mockujemy strukturalnie wymyslonych danych - parsujemy DOKLADNIE to,
co Open-Meteo naprawde zwrocilo, zeby test wychwycil realny ksztalt
odpowiedzi (jednostki, obecnosc/brak pol), nie wyobrazenie o nim.
"""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
from unittest.mock import patch, MagicMock

from arctic_synoptyk.fetch import _parse_daily_response, fetch_archive
from arctic_synoptyk.station import LONGYEARBYEN

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def test_parse_real_forecast_fixture():
    payload = _load_fixture("arctic_forecast_result.json")
    rows = _parse_daily_response(payload)
    assert len(rows) == 7
    first = rows[0]
    assert first["date"] == "2026-08-26"
    assert first["temp_max_c"] == 3.8
    assert first["temp_min_c"] == 0.5
    # avg = (3.8+0.5)/2 = 2.15
    assert first["temp_avg_c_approx"] == 2.15


def test_parse_real_archive_fixture():
    payload = _load_fixture("arctic_archive_result.json")
    rows = _parse_daily_response(payload)
    assert len(rows) == 11
    assert rows[0]["date"] == "2026-08-16"
    assert rows[-1]["date"] == "2026-08-26"


def test_no_missing_values_in_august_fixtures():
    """Nie jestesmy jeszcze w nocy polarnej (listopad-luty) - sprawdzamy,
    ze w tym oknie (sierpien) nie ma dziur w danych. NIE dowodzi to, ze
    zima tez ich nie bedzie - patrz README, "Czego NIE sprawdzono"."""
    for fixture in ("arctic_forecast_result.json", "arctic_archive_result.json"):
        rows = _parse_daily_response(_load_fixture(fixture))
        for r in rows:
            for key in ("temp_min_c", "temp_max_c", "precip_mm", "wind_kmh", "pressure_hpa"):
                assert r[key] is not None, f"{fixture}: brak {key} dla {r['date']}"


def test_parse_raises_keyerror_on_missing_daily_key():
    """Zamiast cicho zwrocic pusta liste przy zmianie ksztaltu odpowiedzi
    API (patrz timdr-signal-framework SS4 o cichych awariach schematu)."""
    import pytest
    with pytest.raises(KeyError):
        _parse_daily_response({"nie_ma_daily": True})


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_fetch_archive_excludes_trailing_unreliable_days():
    """Rdzen bugu znalezionego na realnym uzyciu (2026-08-27): fixture
    archiwum pobrany 2026-08-26 konczy sie na target_date=2026-08-26 (czyli
    "dzis" wzgledem pull'a) - Open-Meteo dla tak swiezej daty zwraca ta sama
    liczbe co prognoza, nie sfinalizowana reanalize. Z domyslnym
    exclude_trailing_days=2 ostatnie 2 dni (2026-08-26, 2026-08-25) maja
    zostac odciete."""
    payload = _load_fixture("arctic_archive_result.json")
    with patch("arctic_synoptyk.fetch.requests.get", return_value=_mock_response(payload)):
        rows = fetch_archive(LONGYEARBYEN, past_days=10, _today=date(2026, 8, 26))
    dates = [r["date"] for r in rows]
    assert "2026-08-26" not in dates
    assert "2026-08-25" not in dates
    assert dates[-1] == "2026-08-24"
    assert dates[0] == "2026-08-16"  # najstarsze dni zostaja nietkniete


def test_fetch_archive_exclude_trailing_days_zero_keeps_everything():
    payload = _load_fixture("arctic_archive_result.json")
    with patch("arctic_synoptyk.fetch.requests.get", return_value=_mock_response(payload)):
        rows = fetch_archive(LONGYEARBYEN, past_days=10, exclude_trailing_days=0, _today=date(2026, 8, 26))
    dates = [r["date"] for r in rows]
    assert "2026-08-26" in dates
    assert len(dates) == 11
