"""
run_arctic.py — codzienny runner do uruchamiania NA LAPTOPIE (nie w
sandboksie Claude, patrz README) - pobiera prognozę i archiwum dla
WSZYSTKICH stacji z `arctic_synoptyk.station.STATIONS` (patrz
"Wiele stacji" niżej), loguje do WSPÓLNEGO CSV (kolumna `station`
rozróżnia wiersze - `bias.py`/`snapshots.py` już filtrowały po niej od
początku, więc dodanie kolejnych stacji nie wymagało zmian w tych
modułach), i pokazuje aktualny status korekty obciążenia per stacja
(pusty, dopóki nie zbierze się min_samples par na dany lead_days).

Uzycie (z folderu SYNOPTYK-ARCTIC):
    python run_arctic.py

Uruchamiaj raz dziennie (np. jako zaplanowane zadanie), zeby CSV
naprawde naros3 do punktu, w ktorym compute_lead_bias() zacznie cos
zwracac - analogicznie do krakow_forecast_snapshots.csv, ktore potrzebowalo
tygodni regularnych uruchomien, zeby dojsc do 1236 par.

## Wiele stacji (dodane 2026-08-31)

Pierwotnie ten moduł obsługiwał tylko Longyearbyen - `collect()` (funkcja
dla JEDNEJ stacji, współdzielona z `POST /api/collect` w dashboardzie,
gdzie użytkownik wybiera stację z listy) zostaje BEZ ZMIAN. Nowe:
`collect_all()` woła `collect()` w pętli po `STATIONS` - to jest ścieżka,
której używa `main()`/`run.bat`/zaplanowane zadanie, żeby JEDNO codzienne
uruchomienie zebrało dane dla wszystkich stacji naraz, bez konieczności
mnożenia zaplanowanych zadań per stacja."""
import sys
from datetime import date
from typing import Callable

from arctic_synoptyk.station import LONGYEARBYEN, STATIONS
from arctic_synoptyk.fetch import fetch_forecast, fetch_archive
from arctic_synoptyk.snapshots import append_snapshot
from arctic_synoptyk.bias import compute_lead_bias
from arctic_synoptyk.retention import prune_old_rows, DEFAULT_KEEP_DAYS

CSV_PATH = "arctic_forecast_snapshots.csv"
STATION = LONGYEARBYEN


def collect(
    csv_path: str = CSV_PATH,
    station=STATION,
    keep_days: int = DEFAULT_KEEP_DAYS,
    _fetch_forecast: Callable = fetch_forecast,
    _fetch_archive: Callable = fetch_archive,
) -> dict:
    """Pobiera prognoze + archiwum i dopisuje do CSV - JEDNO miejsce z ta
    logika, uzywane zarowno przez `main()` (CLI/`run.bat`) jak i przez
    `webapp.app`'s `POST /api/collect` (przycisk "Pobierz nowe dane teraz"
    w dashboardzie) - zeby obie sciezki uzycia robily DOKLADNIE to samo,
    bez duplikowania logiki, ktora moglaby sie rozjechac.

    Po dopisaniu przycina CSV do ostatnich `keep_days` dni (patrz
    `arctic_synoptyk/retention.py` - nic nie kasuje bezpowrotnie, stare
    wiersze ida do pliku archiwalnego), zeby plik roboczy nie rosl w
    nieskonczonosc przy codziennym uruchamianiu.

    `_fetch_forecast`/`_fetch_archive` wstrzykiwalne do testow (ten sam
    wzorzec co `backfill_real_history.backfill()`) - bez tego collect()
    zawsze robilby zywe zapytanie do Open-Meteo, niemozliwe do
    przetestowania w tym srodowisku.

    Zwraca dict (nie printuje) - wywolujacy (CLI albo API) decyduje, jak
    to pokazac."""
    today = date.today()
    station_name = station.name

    forecast_error = None
    try:
        forecast_rows = _fetch_forecast(station, forecast_days=7)
    except Exception as e:
        forecast_error = str(e)
        forecast_rows = []

    archive_error = None
    try:
        archive_rows = _fetch_archive(station, past_days=10)
    except Exception as e:
        archive_error = str(e)
        archive_rows = []

    n_fc = append_snapshot(csv_path, station_name, forecast_rows, issue_date=today, source="prognoza")
    n_arch = append_snapshot(csv_path, station_name, archive_rows, issue_date=today, source="archiwum_openmeteo")

    n_pruned = prune_old_rows(csv_path, keep_days=keep_days)

    bias = compute_lead_bias(csv_path, station_name)
    raw = compute_lead_bias(csv_path, station_name, min_samples=1) if not bias else None

    return {
        "date": today.isoformat(),
        "station": station_name,
        "n_forecast_added": n_fc,
        "n_archive_added": n_arch,
        "n_pruned": n_pruned,
        "forecast_error": forecast_error,
        "archive_error": archive_error,
        "bias": bias,
        "raw_counts": {lead: v["n"] for lead, v in raw.items()} if raw else None,
    }


def collect_all(
    csv_path: str = CSV_PATH,
    stations: list = STATIONS,
    keep_days: int = DEFAULT_KEEP_DAYS,
    _fetch_forecast: Callable = fetch_forecast,
    _fetch_archive: Callable = fetch_archive,
) -> list[dict]:
    """collect() dla KAZDEJ stacji z `stations`, po kolei, do WSPOLNEGO
    `csv_path` - patrz "Wiele stacji" w docstringu modulu. Zwraca liste
    wynikow (jeden dict na stacje, ten sam ksztalt co collect()), zeby
    main() mogl wypisac raport per stacja.

    `prune_old_rows()` (wewnatrz kazdego collect()) jest wolane raz na
    stacje - troche nadmiarowe (caly plik czytany/zapisywany N razy przy
    N stacjach), ale CSV jest maly (retencja 30 dni) i nie warto tu
    optymalizowac kosztem prostoty."""
    return [
        collect(
            csv_path=csv_path,
            station=station,
            keep_days=keep_days,
            _fetch_forecast=_fetch_forecast,
            _fetch_archive=_fetch_archive,
        )
        for station in stations
    ]


def _print_result(result: dict) -> None:
    today, station_name = result["date"], result["station"]

    if result["forecast_error"]:
        print(f"BLAD pobierania prognozy: {result['forecast_error']}")
    if result["archive_error"]:
        print(f"BLAD pobierania archiwum: {result['archive_error']}")

    print(f"[{today}] {station_name}: dopisano {result['n_forecast_added']} wierszy prognozy "
          f"+ {result['n_archive_added']} wierszy archiwum")
    if result["n_pruned"]:
        print(f"           przeniesiono {result['n_pruned']} wierszy starszych niz "
              f"{DEFAULT_KEEP_DAYS} dni do pliku archiwalnego (nic nie skasowano)")

    bias = result["bias"]
    if bias:
        print("Aktualna korekta obciazenia (lead_days -> bias/MAE/n):")
        for lead in sorted(bias):
            e = bias[lead]
            print(f"  lead_days={lead}: bias={e['bias']:+.2f} MAE={e['mae']:.2f} n={e['n']}")
    else:
        print("Korekta jeszcze niedostepna - za malo sparowanych dni w CSV "
              "(potrzeba min. 5 par na dany lead_days, patrz README).")
        raw = result["raw_counts"]
        if raw:
            print("Dotychczasowy postep (surowe liczniki n, NIE wynik trafnosci):")
            for lead in sorted(raw):
                print(f"  lead_days={lead}: n={raw[lead]} / 5")
        else:
            print("Jeszcze zero sparowanych dni (prognoza vs. pozniejsze archiwum "
                  "dla tej samej daty) - normalne w pierwszych ~2 dniach zbierania, "
                  "patrz README ('dlaczego archiwum wyklucza ostatnie 2 dni').")


def main():
    results = collect_all()
    for i, result in enumerate(results):
        if i > 0:
            print()
        _print_result(result)


if __name__ == "__main__":
    sys.exit(main())
