"""
backfill_real_history.py — URUCHOMIĆ NA LAPTOPIE (nie w sandboksie — patrz
`backtest_real.py`, ten sam powód: Previous Runs API i Archive API są
zablokowane w środowisku deweloperskim).

RÓŻNICA vs `backtest_real.py`: `backtest_real.py` tylko DRUKUJE wynik na
konsoli, nic nie zapisuje. Ten skrypt DOPISUJE te same, prawdziwe,
historyczne pary prognoza/rzeczywistość (Previous Runs API + Archive API)
do `arctic_forecast_snapshots.csv`, pod tymi samymi etykietami `source` co
`run_arctic.py` ("prognoza"/"archiwum_openmeteo") — więc
`compute_lead_bias()` i dashboard (`/api/real_bias`) widzą wynik od razu,
zamiast czekać tygodniami na codzienne zbieranie (patrz `README.md`,
"mam 5 dni i nic nie policzyło" — do jednego lead_days trzeba >= 5
sparowanych dni, a każdy dzień daje najwyżej jedną taką parę na raz).

ŚWIADOMY KOMPROMIS: to miesza dane z żywego, codziennego zbierania z
jednorazowym historycznym backfillem POD TYMI SAMYMI etykietami source —
w odróżnieniu od reszty projektu, gdzie każde źródło ma jednoznaczną,
osobną etykietę (np. dane demo mają zawsze `_DEMO` w nazwie stacji, patrz
`demo_synthetic_fill.py`). Uznano to za akceptowalne, bo oba źródła są tu
PRAWDZIWE (nie syntetyczne) i tą samą wielkością (dobowe maksimum z
Open-Meteo) — traci się tylko możliwość odróżnienia po samym CSV "zebrane
dziś na żywo" od "dociągnięte z historii". Idempotentny klucz
`append_snapshot()` nadal chroni przed duplikatami, gdyby backfill
uruchomiono więcej niż raz albo obok już działającego `run_arctic.py`.

Ograniczenie: Previous Runs API (`previous_runs.py`) pyta tylko o
temperaturę (`temperature_2m_previous_dayN`) — backfillowane wiersze
"prognoza" mają wypełnione WYŁĄCZNIE `temp_max_c` (min/avg/precip/
pressure/wind zostają puste, tak jak w każdym innym niekompletnym wierszu
w tym CSV). Wiersze "archiwum_openmeteo" mają komplet pól — `fetch_archive()`
zwraca wszystko.

RETENCJA: po zapisie CSV jest przycinany do ostatnich `keep_days` dni
(domyślnie 30, patrz `arctic_synoptyk/retention.py` — nic nie kasuje
bezpowrotnie, stare wiersze idą do pliku archiwalnego). Stąd domyślne
`past_days=30` TUTAJ, nie 90 — nie ma sensu pobierać dalszej historii,
skoro i tak zostanie od razu przycięta. Podaj większe `past_days` tylko
razem z większym `keep_days` (patrz `main()`/CLI), jeśli świadomie chcesz
trzymać dłuższe okno.

Użycie:
    python backfill_real_history.py [liczba_dni] [keep_days]
    python backfill_real_history.py            # domyślnie 30 dni historii, retencja 30 dni
    python backfill_real_history.py 90 90       # świadomie dłuższe okno obu naraz
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable

from arctic_synoptyk.station import ArcticStation, LONGYEARBYEN
from arctic_synoptyk.fetch import fetch_archive
from arctic_synoptyk.previous_runs import fetch_previous_runs, daily_max_by_lead, MAX_LEAD_DAYS
from arctic_synoptyk.snapshots import append_snapshot
from arctic_synoptyk.retention import prune_old_rows, DEFAULT_KEEP_DAYS

CSV_PATH = "arctic_forecast_snapshots.csv"
DEFAULT_PAST_DAYS = DEFAULT_KEEP_DAYS  # 30 - patrz "RETENCJA" wyzej


def _forecast_record(target_date_str: str, temp_max: float) -> dict[str, Any]:
    """Rekord w kształcie oczekiwanym przez append_snapshot() - tylko
    temp_max_c wypełnione, reszta pusta (patrz zastrzeżenie w docstringu
    modułu o zakresie pól Previous Runs API)."""
    return {
        "date": target_date_str,
        "temp_min_c": "",
        "temp_avg_c_approx": "",
        "temp_max_c": temp_max,
        "precip_mm": "",
        "pressure_hpa": "",
        "wind_kmh": "",
    }


def build_prognoza_groups(by_lead: dict[int, dict[str, float]]) -> dict[date, list[dict]]:
    """Czysta funkcja: wyjście daily_max_by_lead() -> {issue_date: [rekordy]}
    gotowe do append_snapshot() (jedno wywołanie na issue_date, bo
    append_snapshot przyjmuje jeden issue_date na cały pull). Wydzielona z
    backfill(), żeby dało się przetestować samą logikę grupowania/przesunięcia
    dat bez żywego zapytania do API.

    issue_date = target_date - lead_days, żeby lead_days przeliczone przez
    append_snapshot()/_lead_days() zgadzało się z lead_days, pod którym
    Previous Runs API faktycznie zwróciło tę wartość."""
    groups: dict[date, list[dict]] = defaultdict(list)
    for lead, by_date in by_lead.items():
        for target_date_str, temp_max in by_date.items():
            target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
            issue = target - timedelta(days=lead)
            groups[issue].append(_forecast_record(target_date_str, temp_max))
    return groups


def backfill(
    csv_path: str,
    station: ArcticStation,
    past_days: int = DEFAULT_PAST_DAYS,
    max_lead_days: int = MAX_LEAD_DAYS,
    keep_days: int = DEFAULT_KEEP_DAYS,
    _fetch_previous_runs: Callable = fetch_previous_runs,
    _fetch_archive: Callable = fetch_archive,
) -> dict[str, Any]:
    """Pobiera realną historię (Previous Runs + Archive) i dopisuje do
    `csv_path`. `_fetch_previous_runs`/`_fetch_archive` wstrzykiwalne do
    testów (ten sam wzorzec co `run_arctic.collect()` - jedno miejsce z
    logiką, używane zarówno przez CLI (`main()`) jak i przez testy z
    podstawionym fetcherem, bez duplikowania kroku zapisu do CSV).
    `max_lead_days` przekazywane wprost do daily_max_by_lead() - głównie
    do testów, żeby fixture nie musiał udawać wszystkich 7 pól lead_days
    naraz (patrz test_backfill_real_history.py). Po zapisie przycina CSV
    do ostatnich `keep_days` dni (patrz "RETENCJA" w docstringu modułu)."""
    payload = _fetch_previous_runs(station, past_days=past_days)
    by_lead = daily_max_by_lead(payload, max_lead_days=max_lead_days)

    archive_rows = _fetch_archive(station, past_days=past_days, exclude_trailing_days=2)

    # Archiwum: kompletne wiersze wprost z fetch_archive(), jeden issue_date
    # "dzisiaj" dla całego backfillu - klucz idempotentności to (station,
    # target_date, issue_date, source), więc ponowne uruchomienie backfillu
    # tego samego dnia nic nie zduplikuje.
    n_arch = append_snapshot(csv_path, station.name, archive_rows, issue_date=date.today(), source="archiwum_openmeteo")

    groups = build_prognoza_groups(by_lead)
    n_fc = 0
    for issue, records in groups.items():
        n_fc += append_snapshot(csv_path, station.name, records, issue_date=issue, source="prognoza")

    n_pruned = prune_old_rows(csv_path, keep_days=keep_days)

    return {
        "n_forecast_added": n_fc,
        "n_archive_added": n_arch,
        "n_issue_dates": len(groups),
        "n_pruned": n_pruned,
    }


def main() -> int:
    past_days = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PAST_DAYS
    keep_days = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_KEEP_DAYS
    station = LONGYEARBYEN

    print(f"=== Backfill realnej historii do {CSV_PATH}, {station.name}, "
          f"{past_days} dni historii, retencja {keep_days} dni ===\n")
    if past_days > keep_days:
        print(f"UWAGA: past_days ({past_days}) > keep_days ({keep_days}) - "
              f"wiekszosc dopisanych par zostanie od razu przycieta do pliku "
              f"archiwalnego (patrz docstring modulu, sekcja RETENCJA).\n")
    print("[1/2] Pobieram Previous Runs API + Archive API...")
    try:
        result = backfill(CSV_PATH, station, past_days=past_days, keep_days=keep_days)
    except Exception as e:
        print(f"BLAD pobierania/zapisu: {e}")
        return 1

    print(f"[2/2] Dopisano {result['n_forecast_added']} wierszy prognozy "
          f"(w {result['n_issue_dates']} grupach issue_date) + "
          f"{result['n_archive_added']} wierszy archiwum "
          f"(pominięto już istniejące — klucz idempotentności).")
    if result["n_pruned"]:
        print(f"          przeniesiono {result['n_pruned']} wierszy starszych niz "
              f"{keep_days} dni do pliku archiwalnego (nic nie skasowano).")
    print("\nSprawdź teraz `pytest -v` i dashboard (/api/real_bias) — powinny "
          "pokazać wynik od razu, bez czekania na kolejne dni run_arctic.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
