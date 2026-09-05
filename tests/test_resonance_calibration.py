"""
test_resonance_calibration.py — testy arctic_synoptyk/resonance_calibration.py.

Konwencja jak w tests/test_bias.py: budujemy tymczasowy CSV przez
append_snapshot() (prawdziwa funkcja zapisu z arctic_synoptyk/snapshots.py,
nie recznie sklejany CSV), zeby test przechodzil dokladnie te sama sciezke
co produkcyjny kod. Dwa glowne scenariusze (ten sam duch co siostrzany
synoptyk-v2.0/forecaster/test_resonance_calibration.py):

  1. TestCalibratedCase - dni oflagowane jako rezonansowe MAJA faktycznie
     wyzszy blad prognozy -> kalibracja sie wlacza.
  2. TestInsufficientData - za malo sparowanych dni w ktorejs z grup (albo
     CSV nie istnieje/pusty) -> "brak mocy testu", confidence_multiplier
     wraca do 1.0, status="insufficient_data". To jest REALISTYCZNY,
     CZESTY przypadek dla wiekszosci z 10 stacji tego repo (30-dniowa
     retencja CSV, limity API dzielone miedzy stacje) - patrz docstring
     resonance_calibration.py.
"""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from arctic_synoptyk.resonance_calibration import (
    DEFAULT_CONFIDENCE_MULTIPLIER,
    calibrate_resonance,
    get_resonance_confidence_multiplier,
)
from arctic_synoptyk.snapshots import append_snapshot

STATION = "Test_Stacja"


def _rec(target_date, temp_max, pressure=1010.0, precip=0.0, wind=10.0):
    return {"date": target_date, "temp_min_c": temp_max - 3, "temp_avg_c_approx": temp_max - 1.5,
            "temp_max_c": temp_max, "precip_mm": precip, "wind_kmh": wind, "pressure_hpa": pressure}


def _build_scenario_csv(csv_path: str, n_normal: int = 40, n_flagged: int = 8) -> None:
    """
    n_normal dni "spokojnych" (temp~5 real, forecast ~4.5 - blisko siebie,
    maly blad) + n_flagged dni ze SKOKIEM na WSZYSTKICH czterech kanalach
    jednoczesnie (temp/pressure/precip/wind) I duzym bledem prognozy (real
    bardzo daleko od forecast) - dokladnie sytuacja, w ktorej prawdziwy
    rezonans (>=3 anomalne kanaly) powinien korelowac z gorsza prognoza.
    Wartosci szczytowe dobrane z duzym zapasem nad mean +/- 2*std (patrz
    siostrzany test w synoptyk-v2.0 - te same rzedy wielkosci)."""
    day = 0
    for i in range(max(n_normal, n_flagged)):
        if i < n_flagged:
            target = f"2026-{(day // 28) + 1:02d}-{(day % 28) + 1:02d}"
            issue = f"2026-{(day // 28) + 1:02d}-{max(1, (day % 28)):02d}"
            append_snapshot(csv_path, STATION, [_rec(target, 40.0)],
                             issue_date=date.fromisoformat(issue), source="prognoza")
            append_snapshot(csv_path, STATION,
                             [_rec(target, 80.0, pressure=700.0, precip=500.0, wind=300.0)],
                             issue_date=date.fromisoformat(target), source="archiwum_openmeteo")
            day += 1
        if i < n_normal:
            target = f"2026-{(day // 28) + 1:02d}-{(day % 28) + 1:02d}"
            issue = f"2026-{(day // 28) + 1:02d}-{max(1, (day % 28)):02d}"
            append_snapshot(csv_path, STATION, [_rec(target, 4.5)],
                             issue_date=date.fromisoformat(issue), source="prognoza")
            append_snapshot(csv_path, STATION, [_rec(target, 5.0)],
                             issue_date=date.fromisoformat(target), source="archiwum_openmeteo")
            day += 1


class TestCalibratedCase:
    def test_calibration_detects_resonance_effect(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = os.path.join(d, "arctic.csv")
            _build_scenario_csv(csv_path, n_normal=40, n_flagged=8)
            result = calibrate_resonance(csv_path, STATION, min_samples_per_group=8)
            assert result["status"] == "calibrated"
            assert result["n_resonance_days"] == 8
            assert result["n_normal_days"] == 40
            # blad: normalne |5.0-4.5|=0.5, rezonansowe |80-40|=40.0
            assert result["mae_normal"] == pytest.approx(0.5, abs=1e-6)
            assert result["mae_resonance"] == pytest.approx(40.0, abs=1e-6)
            # duza roznica bledow -> mnoznik podbity do sufitu (3.0)
            assert result["confidence_multiplier"] == pytest.approx(3.0)
            # ratio >> 2.0 -> rekomendacja zlagodzenia progu K
            assert result["recommended_k"] == 2

    def test_get_resonance_confidence_multiplier_matches_calibrate_resonance(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = os.path.join(d, "arctic.csv")
            _build_scenario_csv(csv_path, n_normal=40, n_flagged=8)
            full = calibrate_resonance(csv_path, STATION, min_samples_per_group=8)
            multiplier = get_resonance_confidence_multiplier(csv_path, STATION, min_samples_per_group=8)
            assert multiplier == full["confidence_multiplier"]


class TestInsufficientData:
    def test_too_few_resonance_days_falls_back_to_default(self):
        # tylko 3 dni "rezonansowe" (proxy) wsrod 20 normalnych - ponizej
        # progu min_samples_per_group=8 dla grupy rezonansowej. To jest
        # OCZEKIWANY stan dla wiekszosci stacji tego repo wiekszosc czasu
        # (30-dniowa retencja CSV, 10 stacji) - patrz docstring modulu.
        with tempfile.TemporaryDirectory() as d:
            csv_path = os.path.join(d, "arctic.csv")
            _build_scenario_csv(csv_path, n_normal=20, n_flagged=3)
            result = calibrate_resonance(csv_path, STATION, min_samples_per_group=8)
            assert result["status"] == "insufficient_data"
            assert result["confidence_multiplier"] == DEFAULT_CONFIDENCE_MULTIPLIER
            assert result["n_resonance_days"] < 8
            assert "reason" in result

    def test_missing_file_returns_safe_default_without_raising(self):
        result = calibrate_resonance("/nonexistent/path/does_not_exist.csv", STATION)
        assert result["status"] == "insufficient_data"
        assert result["confidence_multiplier"] == DEFAULT_CONFIDENCE_MULTIPLIER

    def test_no_paired_data_returns_safe_default(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = os.path.join(d, "arctic.csv")
            # tylko prognoza, brak wiersza "archiwum_openmeteo" - nic do sparowania
            append_snapshot(csv_path, STATION, [_rec("2026-08-27", 5.0)],
                             issue_date=date(2026, 8, 26), source="prognoza")
            result = calibrate_resonance(csv_path, STATION)
            assert result["status"] == "insufficient_data"
            assert result["confidence_multiplier"] == DEFAULT_CONFIDENCE_MULTIPLIER

    def test_wrapper_never_raises_and_returns_default_on_missing_file(self):
        multiplier = get_resonance_confidence_multiplier("/nonexistent/path.csv", STATION)
        assert multiplier == DEFAULT_CONFIDENCE_MULTIPLIER

    def test_different_station_not_mixed_in(self):
        # Stacja z DUZO danych, ale pod inna nazwa - `station` musi
        # faktycznie filtrowac, nie przyjmowac wszystkiego z CSV (ten sam
        # duch co tests/test_bias.py::test_different_station_names_not_mixed).
        with tempfile.TemporaryDirectory() as d:
            csv_path = os.path.join(d, "arctic.csv")
            _build_scenario_csv(csv_path, n_normal=40, n_flagged=8)
            result = calibrate_resonance(csv_path, "Inna_Stacja_Ktorej_Nie_Ma")
            assert result["status"] == "insufficient_data"


class TestConfidenceMultiplierFloor:
    def test_multiplier_never_drops_below_one_even_if_resonance_days_look_better(self):
        # scenariusz odwrotny: dni "rezonansowe" (proxy) maja MNIEJSZY blad
        # prognozy niz normalne - rezonans z definicji ma tylko poszerzac
        # niepewnosc, nigdy jej nie zwezac ponizej bazowego poziomu.
        #
        # UWAGA na proporcje grup: n_flagged musi zostac WYRAZNA MNIEJSZOSCIA
        # calego okna (tu 8 z 48, tak samo jak w _build_scenario_csv) - gdy
        # grupa "flagged" jest zbyt liczna wzgledem "normal" (np. 8 z 28),
        # mean+/-2*std calego okna sie poszerza na tyle, ze ekstremalne
        # wartosci przestaja wypadac poza prog i test milczaco przestaje
        # cokolwiek sprawdzac (zadny dzien nie zostaje oflagowany jako
        # rezonansowy). 8:40 to ten sam bezpieczny margines, co juz
        # zweryfikowany w _build_scenario_csv/TestCalibratedCase.
        with tempfile.TemporaryDirectory() as d:
            csv_path = os.path.join(d, "arctic.csv")

            def _target_and_issue(c):
                month, dom = (c // 28) + 1, (c % 28) + 1
                target = f"2026-{month:02d}-{dom:02d}"
                issue = date(2026, month, max(1, dom - 1))
                return target, issue

            # 8 dni "rezonansowych" - prognoza TRAFIA idealnie (blad=0).
            for c in range(8):
                target, issue = _target_and_issue(c)
                append_snapshot(csv_path, STATION, [_rec(target, 80.0)],
                                 issue_date=issue, source="prognoza")
                append_snapshot(csv_path, STATION,
                                 [_rec(target, 80.0, pressure=700.0, precip=500.0, wind=300.0)],
                                 issue_date=issue, source="archiwum_openmeteo")
            # 40 dni "normalnych" - prognoza SYSTEMATYCZNIE nietrafiona (blad=5).
            for c in range(8, 48):
                target, issue = _target_and_issue(c)
                append_snapshot(csv_path, STATION, [_rec(target, 10.0)],
                                 issue_date=issue, source="prognoza")
                append_snapshot(csv_path, STATION, [_rec(target, 5.0)],
                                 issue_date=issue, source="archiwum_openmeteo")
            result = calibrate_resonance(csv_path, STATION, min_samples_per_group=8)
            assert result["status"] == "calibrated"
            assert result["n_resonance_days"] == 8
            assert result["n_normal_days"] == 40
            assert result["mae_resonance"] < result["mae_normal"]
            assert result["confidence_multiplier"] == pytest.approx(1.0)
