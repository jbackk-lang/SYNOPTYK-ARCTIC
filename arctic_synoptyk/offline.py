"""
offline.py — Etap 2: warstwa odporna na przerwy w łączności.

Kluczowe rozróżnienie, którego brakowało w Synoptyk-v2.0 (patrz README
głównego repo, sekcja o Arktyce): PRZYRZĄD POMIAROWY i ŁĄCZNOŚĆ to dwie
osobne rzeczy. Prawdziwa automatyczna stacja arktyczna zwykle ma zasilanie
(solar+bateria) i loguje odczyty LOKALNIE cały czas, nawet gdy łącze
satelitarne (Iridium/Argos) jest niedostępne przez dni czy tygodnie — dane
czekają w lokalnym buforze i wysyłają się przy najbliższej okazji.

`_load_csv_history_fallback()` w Synoptyk-v2.0 (gui_app.py) nie ma tego
rozróżnienia - zakłada, że jeśli nie ma świeżego Open-Meteo, to nie ma
NICZEGO świeższego niż to, co już zdążyło trafić do CSV przy wcześniejszych
udanych połączeniach. Dla Arktyki to złe założenie: stacja MOŻE mieć
świeże, lokalne odczyty, mimo że nie da się ich jeszcze wysłać.

Ten moduł modeluje to rozróżnienie:
- `LocalBuffer` — trwały, lokalny log odczytów z przyrządu (JSONL,
  append-only), niezależny od tego, czy łączność akurat działa.
- `StalenessLevel` / `classify_staleness()` — jawny wskaźnik "jak stare są
  najświeższe dane, na których operujemy", z progami dopasowanymi do
  realistycznych przerw satelitarnych (dni-tygodnie), nie do
  "chwilowego zerwania Wi-Fi" jak w oryginalnym CSV fallbacku Krakowa.
- `degraded_forecast()` — gdy nie ma świeżej prognozy z Open-Meteo,
  buduje NAJPROSTSZĄ uczciwą estymację z lokalnego bufora (persystencja:
  "jutro podobnie jak ostatnio zmierzone"), zamiast próbować odtworzyć
  filtr falkowy/SynoptykV4 na potencjalnie dziurawym sygnale.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class InstrumentReading:
    """Jeden lokalny odczyt z przyrządu stacji - niezależny od tego, czy
    dało się go już wysłać przez łącze satelitarne."""
    timestamp: str  # ISO 8601, np. "2026-08-26T12:00:00"
    temp_c: float
    pressure_hpa: Optional[float] = None
    wind_kmh: Optional[float] = None
    precip_mm: Optional[float] = None


class StalenessLevel(Enum):
    FRESH = "fresh"          # < 1 dzien od ostatniej udanej synchronizacji
    AGING = "aging"          # 1-3 dni
    STALE = "stale"          # 3-14 dni
    CRITICAL = "critical"    # > 14 dni

    @property
    def label_pl(self) -> str:
        return {
            StalenessLevel.FRESH: "🟢 świeże",
            StalenessLevel.AGING: "🟡 starzejące się",
            StalenessLevel.STALE: "🟠 nieaktualne",
            StalenessLevel.CRITICAL: "🔴 krytycznie nieaktualne",
        }[self]


def classify_staleness(last_update: datetime, now: datetime) -> StalenessLevel:
    """Progi dobrane pod realistyczne przerwy łączności satelitarnej
    (dni-tygodnie), NIE pod "kilka minut" jak typowy wskaźnik świeżości
    danych w systemie z ciągłym internetem. Ujemny wiek (last_update > now)
    traktowany jak FRESH (zegar/strefa czasowa, nie powód do alarmu)."""
    age = now - last_update
    if age <= timedelta(days=1):
        return StalenessLevel.FRESH
    if age <= timedelta(days=3):
        return StalenessLevel.AGING
    if age <= timedelta(days=14):
        return StalenessLevel.STALE
    return StalenessLevel.CRITICAL


class LocalBuffer:
    """Trwały, lokalny bufor odczytów - JSONL (jeden odczyt na linię),
    żeby dopisywanie było odporne na przerwanie procesu w połowie (w
    odróżnieniu od jednego dużego pliku JSON, gdzie ucięty zapis psuje
    cały plik)."""

    def __init__(self, path: str):
        self.path = path

    def append_reading(self, reading: InstrumentReading) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(reading)) + "\n")

    def all_readings(self) -> list[InstrumentReading]:
        if not os.path.isfile(self.path):
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(InstrumentReading(**json.loads(line)))
        return out

    def latest_reading(self) -> Optional[InstrumentReading]:
        readings = self.all_readings()
        if not readings:
            return None
        return max(readings, key=lambda r: r.timestamp)

    def unsynced_since(self, watermark: Optional[str]) -> list[InstrumentReading]:
        """Odczyty nowsze niz ostatni znany 'watermark' synchronizacji -
        to, co trzeba by wyslac przy najblizszej okazji polaczenia."""
        readings = self.all_readings()
        if watermark is None:
            return readings
        return [r for r in readings if r.timestamp > watermark]

    # --- śledzenie ostatniej udanej synchronizacji (osobny, malutki plik
    # obok bufora - nie miesza się z append-only logiem odczytów) ---

    @property
    def _sync_marker_path(self) -> str:
        return self.path + ".last_sync"

    def record_sync(self, timestamp: str) -> None:
        """Zapisuje znacznik czasu ostatniej udanej synchronizacji
        (połączenia z centralą/API). Wywoływać PO udanym wysłaniu/
        pobraniu, nie przy każdym odczycie z przyrządu."""
        with open(self._sync_marker_path, "w", encoding="utf-8") as f:
            f.write(timestamp)

    def last_sync(self) -> Optional[datetime]:
        if not os.path.isfile(self._sync_marker_path):
            return None
        with open(self._sync_marker_path, encoding="utf-8") as f:
            raw = f.read().strip()
        return datetime.fromisoformat(raw) if raw else None


def degraded_forecast(buffer: LocalBuffer, now: datetime) -> dict:
    """Najprostsza uczciwa estymacja, gdy nie ma świeżej prognozy z
    Open-Meteo: PERSYSTENCJA (ostatni znany odczyt = najlepsza dostępna
    estymacja "teraz"), NIE próba ekstrapolacji trendu na potencjalnie
    dziurawym, rzadkim sygnale z bufora - to celowo prostsze niż
    SynoptykV4.forecast(), bo dane wejściowe są dużo mniej wiarygodne
    (mogą mieć wielodniowe przerwy) niż godzinowy szereg z Open-Meteo.

    Zwraca słownik z jawnym `staleness` i `staleness_label_pl` - żeby
    KAŻDY odbiorca tej wartości wiedział, że to nie świeża prognoza,
    zamiast dowiadywać się tego dopiero z osobnej dokumentacji."""
    latest = buffer.latest_reading()
    if latest is None:
        return {
            "status": "brak_danych",
            "message": "Bufor lokalny pusty - brak jakichkolwiek odczytów do degradowanej estymacji.",
        }

    last_dt = datetime.fromisoformat(latest.timestamp)
    level = classify_staleness(last_dt, now)

    return {
        "status": "degraded_persistence",
        "temp_c": latest.temp_c,
        "pressure_hpa": latest.pressure_hpa,
        "wind_kmh": latest.wind_kmh,
        "precip_mm": latest.precip_mm,
        "based_on_reading_at": latest.timestamp,
        "age": str(now - last_dt),
        "staleness": level.value,
        "staleness_label_pl": level.label_pl,
        "method": "persystencja (ostatni znany lokalny odczyt) - NIE ekstrapolacja trendu",
    }
