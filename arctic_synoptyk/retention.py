"""
retention.py — utrzymuje `arctic_forecast_snapshots.csv` w rozsądnym
rozmiarze. Ten sam wzorzec co Synoptyk-v2.0
(`gui_app.py::_prune_old_csv_rows`): NIC nie kasuje bezpowrotnie — wiersze,
których `target_date` jest starsza niż `keep_days` dni wstecz od dziś, są
NAJPIERW dopisywane do pliku archiwalnego (`*_archive.csv`, ten sam układ
kolumn, nigdy nie przycinany), a dopiero potem usuwane z pliku "gorącego".
Historia jest więc zawsze dostępna do ręcznej analizy — tylko podzielona na
"bieżący log" (mały, szybki do wczytania) i "archiwum" (pełna historia).

Dlaczego 30 dni (domyślnie) wystarcza: `compute_lead_bias()` potrzebuje
>= `min_samples` (5) sparowanych dni PER `lead_days` (max lead=7 w tym
module). Para dla danego `lead_days` pojawia się, gdy jej `target_date` ma
już >= `lead_days + 2` dni (odcięcie niesfinalizowanego archiwum, patrz
`fetch.py::exclude_trailing_days`) — czyli najdłuższy lead (7) potrzebuje
danych sprzed 9 dni. 30-dniowe okno kroczące to ponad 3x zapas nawet dla
najdłuższego horyzontu, przy założeniu ciągłego, codziennego zbierania
(`run_arctic.py`).

CELOWO NIE wpięte do `snapshots.append_snapshot()` — ta funkcja jest
współdzielona z `demo_synthetic_fill.py`, którego dane mają STAŁE,
zmyślone daty (start 2026-08-01) niezwiązane z prawdziwym "dziś".
Automatyczne przycinanie tam ucięłoby demo do przypadkowego, malejącego
z czasem okurchu zamiast pełnej, zamierzonej próbki. Dlatego `prune_old_rows()`
jest wywoływane jawnie tam, gdzie to ma sens: `run_arctic.collect()` i
`backfill_real_history.backfill()` (obie operują na REALNYM
`arctic_forecast_snapshots.csv`), nie z samego `append_snapshot()`.

UWAGA przy backfillu: jeśli `backfill_real_history.py` dostanie
`past_days` większe niż `keep_days` tutaj, większość dopisanych par
zostanie od razu przy najbliższym `prune_old_rows()` przeniesiona do
archiwum — stąd domyślne `past_days=30` w `backfill_real_history.py`,
zgodne z tą retencją."""
from __future__ import annotations

import csv
import os
from datetime import date, datetime, timedelta

# Musi się zgadzać z arctic_synoptyk.snapshots.FIELDNAMES (nie importowane
# stamtąd, żeby uniknąć cyklu retention<->snapshots — test_retention.py
# pilnuje zgodności obu list wprost).
FIELDNAMES = [
    "station", "target_date", "issue_date", "lead_days",
    "temp_min_c", "temp_avg_c_approx", "temp_max_c",
    "precip_mm", "pressure_hpa", "wind_kmh", "source",
]

DEFAULT_KEEP_DAYS = 30
_ARCHIVE_SUFFIX = "_archive.csv"


def archive_path_for(csv_path: str) -> str:
    base, _ext = os.path.splitext(csv_path)
    return base + _ARCHIVE_SUFFIX


def prune_old_rows(csv_path: str, keep_days: int = DEFAULT_KEEP_DAYS, _today: date | None = None) -> int:
    """Przenosi wiersze z `target_date` starszą niż `keep_days` dni do pliku
    archiwalnego (`archive_path_for(csv_path)`), zostawiając w `csv_path`
    tylko te w oknie. Zwraca liczbę przeniesionych wierszy (0, jeśli nic do
    zrobienia — w tym gdy plik nie istnieje albo jest pusty).

    Wiersze z niesparsowalną/brakującą `target_date` są ZAWSZE zachowywane
    w pliku gorącym — nie zgadujemy, czy są stare, patrz ten sam wybór w
    `gui_app.py::_prune_old_csv_rows` dla Krakowa."""
    if not os.path.isfile(csv_path):
        return 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 0

    today = _today if _today is not None else date.today()
    cutoff = today - timedelta(days=keep_days)

    keep_rows: list[dict] = []
    old_rows: list[dict] = []
    for r in rows:
        raw = r.get("target_date")
        try:
            td = datetime.strptime(raw, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            keep_rows.append(r)
            continue
        (keep_rows if td >= cutoff else old_rows).append(r)

    if not old_rows:
        return 0

    archive_path = archive_path_for(csv_path)
    archive_exists = os.path.isfile(archive_path)
    with open(archive_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not archive_exists:
            writer.writeheader()
        writer.writerows(old_rows)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(keep_rows)

    return len(old_rows)
