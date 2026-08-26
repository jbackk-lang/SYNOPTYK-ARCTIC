import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.offline import InstrumentReading, LocalBuffer, StalenessLevel
from arctic_synoptyk.connectivity_sim import connectivity_schedule, run_scenario


def _reading_fn(day_index):
    return InstrumentReading(
        timestamp=(datetime(2026, 8, 1) + timedelta(days=day_index)).isoformat(),
        temp_c=-5.0 + day_index * 0.1,
    )


def test_connectivity_schedule_shape():
    sched = connectivity_schedule(total_days=10, gap_start_day=3, gap_length_days=4)
    assert sched == [True, True, True, False, False, False, False, True, True, True]


def test_connectivity_schedule_rejects_out_of_range_gap():
    import pytest
    with pytest.raises(ValueError):
        connectivity_schedule(total_days=10, gap_start_day=8, gap_length_days=5)


def test_long_gap_does_not_crash_and_buffer_keeps_logging():
    """Rdzen testu: 20-dniowa przerwa w lacznosci (realistyczna dla
    satelitarnego uplinka na Arktyce) NIE powoduje utraty danych ani
    wyjatku - przyrzad loguje lokalnie przez cala przerwe."""
    with tempfile.TemporaryDirectory() as d:
        buf = LocalBuffer(os.path.join(d, "buffer.jsonl"))
        sched = connectivity_schedule(total_days=25, gap_start_day=2, gap_length_days=20)
        results = run_scenario(sched, buf, datetime(2026, 8, 1), _reading_fn)

        assert len(results) == 25
        # przyrzad zalogowal odczyt KAZDEGO dnia, niezaleznie od lacznosci
        assert len(buf.all_readings()) == 25


def test_staleness_escalates_during_gap_and_resets_on_reconnect():
    with tempfile.TemporaryDirectory() as d:
        buf = LocalBuffer(os.path.join(d, "buffer.jsonl"))
        # lacznosc dni 0-1, przerwa dni 2-21 (20 dni), znow lacznosc od dnia 22
        sched = connectivity_schedule(total_days=25, gap_start_day=2, gap_length_days=20)
        results = run_scenario(sched, buf, datetime(2026, 8, 1), _reading_fn)
        by_day = {r.day_index: r for r in results}

        # dzien 1: polaczony -> swiezy sync tego samego dnia -> FRESH
        assert by_day[1].staleness == StalenessLevel.FRESH
        # dzien 2: 1 dzien od ostatniego syncu (dzien1) -> jeszcze FRESH (granica <=1)
        assert by_day[2].staleness == StalenessLevel.FRESH
        # dzien 4: 3 dni od syncu -> AGING
        assert by_day[4].staleness == StalenessLevel.AGING
        # dzien 10: 9 dni od syncu -> STALE
        assert by_day[10].staleness == StalenessLevel.STALE
        # dzien 20: 19 dni od syncu -> CRITICAL
        assert by_day[20].staleness == StalenessLevel.CRITICAL
        # dzien 22: lacznosc wraca -> natychmiast FRESH tego samego dnia
        assert by_day[22].connectivity is True
        assert by_day[22].staleness == StalenessLevel.FRESH


def test_short_gap_never_reaches_critical():
    """Krotka, 'typowa' przerwa (2 dni) - to scenariusz, ktory juz
    obslugiwal CSV fallback w Synoptyk-v2.0. Sprawdzamy, ze tu tez
    dziala i nie eskaluje niepotrzebnie do stanu krytycznego."""
    with tempfile.TemporaryDirectory() as d:
        buf = LocalBuffer(os.path.join(d, "buffer.jsonl"))
        sched = connectivity_schedule(total_days=10, gap_start_day=3, gap_length_days=2)
        results = run_scenario(sched, buf, datetime(2026, 8, 1), _reading_fn)
        assert all(r.staleness != StalenessLevel.CRITICAL for r in results)
