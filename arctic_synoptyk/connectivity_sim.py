"""
connectivity_sim.py — symulacja wielodniowej przerwy w łączności, do
testów (nie mam dostępu do prawdziwego sprzętu stacji ani prawdziwego
łącza satelitarnego, żeby to sprawdzić inaczej niż symulacją - jawnie
przyznane w README).

Model: KAŻDEGO dnia przyrząd loguje odczyt lokalnie (zasilanie solar+
+bateria działa niezależnie od łącza). ŁĄCZNOŚĆ (osobna zmienna) bywa
niedostępna przez ciągły odcinek dni (typowe dla łącza satelitarnego -
przerwy pogodowe/orbitalne/awaryjne, nie pojedyncze zerwane pakiety).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .offline import InstrumentReading, LocalBuffer, classify_staleness, StalenessLevel


def connectivity_schedule(total_days: int, gap_start_day: int, gap_length_days: int) -> list[bool]:
    """Zwraca liste dlugosci total_days: True = lacznosc dostepna tego
    dnia, False = przerwa. Przerwa to jeden ciagly odcinek [gap_start_day,
    gap_start_day+gap_length_days)."""
    if gap_start_day < 0 or gap_start_day + gap_length_days > total_days:
        raise ValueError("przerwa musi miescic sie w zakresie [0, total_days)")
    return [
        not (gap_start_day <= day < gap_start_day + gap_length_days)
        for day in range(total_days)
    ]


@dataclass
class DayResult:
    day_index: int
    date: str
    connectivity: bool
    staleness: StalenessLevel


def run_scenario(
    schedule: list[bool],
    buffer: LocalBuffer,
    start_date: datetime,
    reading_fn: Callable[[int], InstrumentReading],
) -> list[DayResult]:
    """Odtwarza `len(schedule)` dni. Każdego dnia: przyrząd loguje odczyt
    lokalnie (zawsze - to nie zależy od łączności); jeśli tego dnia
    łączność jest dostępna, zapisujemy sync marker na ten dzień. Zwraca
    listę wyników per dzień, w tym poziom nieaktualności NA KONIEC dnia
    (czyli już po ewentualnej synchronizacji tego dnia)."""
    results = []
    for i, connected in enumerate(schedule):
        current_date = start_date + timedelta(days=i)
        reading = reading_fn(i)
        buffer.append_reading(reading)

        if connected:
            buffer.record_sync(current_date.isoformat())

        last_sync = buffer.last_sync()
        staleness = (
            classify_staleness(last_sync, current_date)
            if last_sync is not None
            else StalenessLevel.CRITICAL
        )
        results.append(DayResult(
            day_index=i,
            date=current_date.date().isoformat(),
            connectivity=connected,
            staleness=staleness,
        ))
    return results
