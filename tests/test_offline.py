import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.offline import (
    InstrumentReading, LocalBuffer, StalenessLevel, classify_staleness, degraded_forecast,
)


def test_classify_staleness_thresholds():
    now = datetime(2026, 8, 26, 12, 0, 0)
    assert classify_staleness(now - timedelta(hours=2), now) == StalenessLevel.FRESH
    assert classify_staleness(now - timedelta(days=2), now) == StalenessLevel.AGING
    assert classify_staleness(now - timedelta(days=10), now) == StalenessLevel.STALE
    assert classify_staleness(now - timedelta(days=20), now) == StalenessLevel.CRITICAL


def test_classify_staleness_boundary_exact_1_day_is_fresh():
    now = datetime(2026, 8, 26, 12, 0, 0)
    assert classify_staleness(now - timedelta(days=1), now) == StalenessLevel.FRESH


def test_local_buffer_persists_across_instances():
    """Kluczowe dla realnego scenariusza: proces moze sie zrestartowac
    (np. reset zasilania stacji), bufor musi przetrwac na dysku."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "buffer.jsonl")
        buf1 = LocalBuffer(path)
        buf1.append_reading(InstrumentReading(timestamp="2026-08-26T12:00:00", temp_c=-5.0))

        buf2 = LocalBuffer(path)  # nowa instancja, jakby po restarcie procesu
        readings = buf2.all_readings()
        assert len(readings) == 1
        assert readings[0].temp_c == -5.0


def test_latest_reading_picks_max_timestamp_not_insertion_order():
    with tempfile.TemporaryDirectory() as d:
        buf = LocalBuffer(os.path.join(d, "buffer.jsonl"))
        buf.append_reading(InstrumentReading(timestamp="2026-08-20T00:00:00", temp_c=1.0))
        buf.append_reading(InstrumentReading(timestamp="2026-08-26T00:00:00", temp_c=2.0))
        buf.append_reading(InstrumentReading(timestamp="2026-08-22T00:00:00", temp_c=3.0))
        latest = buf.latest_reading()
        assert latest.timestamp == "2026-08-26T00:00:00"
        assert latest.temp_c == 2.0


def test_unsynced_since_filters_correctly():
    with tempfile.TemporaryDirectory() as d:
        buf = LocalBuffer(os.path.join(d, "buffer.jsonl"))
        for day in (20, 21, 22, 23):
            buf.append_reading(InstrumentReading(timestamp=f"2026-08-{day:02d}T00:00:00", temp_c=0.0))
        pending = buf.unsynced_since("2026-08-21T00:00:00")
        dates = [r.timestamp[:10] for r in pending]
        assert dates == ["2026-08-22", "2026-08-23"]


def test_degraded_forecast_empty_buffer():
    with tempfile.TemporaryDirectory() as d:
        buf = LocalBuffer(os.path.join(d, "buffer.jsonl"))
        result = degraded_forecast(buf, datetime(2026, 8, 26))
        assert result["status"] == "brak_danych"


def test_degraded_forecast_uses_persistence_and_reports_staleness():
    with tempfile.TemporaryDirectory() as d:
        buf = LocalBuffer(os.path.join(d, "buffer.jsonl"))
        buf.append_reading(InstrumentReading(
            timestamp="2026-08-15T00:00:00", temp_c=-8.5, pressure_hpa=1005.0,
            wind_kmh=20.0, precip_mm=0.0,
        ))
        now = datetime(2026, 8, 26)  # 11 dni pozniej -> STALE
        result = degraded_forecast(buf, now)
        assert result["status"] == "degraded_persistence"
        assert result["temp_c"] == -8.5
        assert result["staleness"] == "stale"
        assert "persystencja" in result["method"]
