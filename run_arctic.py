"""
run_arctic.py — codzienny runner do uruchamiania NA LAPTOPIE (nie w
sandboksie Claude, patrz README) - pobiera prognozę i archiwum dla
Longyearbyen, loguje do CSV, i pokazuje aktualny status korekty obciążenia
(pusty, dopóki nie zbierze się min_samples par na dany lead_days).

Uzycie (z folderu SYNOPTYK-ARCTIC):
    python run_arctic.py

Uruchamiaj raz dziennie (np. jako zaplanowane zadanie), zeby CSV
naprawde naros3 do punktu, w ktorym compute_lead_bias() zacznie cos
zwracac - analogicznie do krakow_forecast_snapshots.csv, ktore potrzebowalo
tygodni regularnych uruchomien, zeby dojsc do 1236 par.
"""
import sys
from datetime import date

from arctic_synoptyk.station import LONGYEARBYEN
from arctic_synoptyk.fetch import fetch_forecast, fetch_archive
from arctic_synoptyk.snapshots import append_snapshot
from arctic_synoptyk.bias import compute_lead_bias

CSV_PATH = "arctic_forecast_snapshots.csv"
STATION = LONGYEARBYEN


def collect(csv_path: str = CSV_PATH, station=STATION) -> dict:
    """Pobiera prognoze + archiwum i dopisuje do CSV - JEDNO miejsce z ta
    logika, uzywane zarowno przez `main()` (CLI/`run.bat`) jak i przez
    `webapp.app`'s `POST /api/collect` (przycisk "Pobierz nowe dane teraz"
    w dashboardzie) - zeby obie sciezki uzycia robily DOKLADNIE to samo,
    bez duplikowania logiki, ktora moglaby sie rozjechac.

    Zwraca dict (nie printuje) - wywolujacy (CLI albo API) decyduje, jak
    to pokazac."""
    today = date.today()
    station_name = station.name

    forecast_error = None
    try:
        forecast_rows = fetch_forecast(station, forecast_days=7)
    except Exception as e:
        forecast_error = str(e)
        forecast_rows = []

    archive_error = None
    try:
        archive_rows = fetch_archive(station, past_days=10)
    except Exception as e:
        archive_error = str(e)
        archive_rows = []

    n_fc = append_snapshot(csv_path, station_name, forecast_rows, issue_date=today, source="prognoza")
    n_arch = append_snapshot(csv_path, station_name, archive_rows, issue_date=today, source="archiwum_openmeteo")

    bias = compute_lead_bias(csv_path, station_name)
    raw = compute_lead_bias(csv_path, station_name, min_samples=1) if not bias else None

    return {
        "date": today.isoformat(),
        "station": station_name,
        "n_forecast_added": n_fc,
        "n_archive_added": n_arch,
        "forecast_error": forecast_error,
        "archive_error": archive_error,
        "bias": bias,
        "raw_counts": {lead: v["n"] for lead, v in raw.items()} if raw else None,
    }


def main():
    result = collect()
    today, station_name = result["date"], result["station"]

    if result["forecast_error"]:
        print(f"BLAD pobierania prognozy: {result['forecast_error']}")
    if result["archive_error"]:
        print(f"BLAD pobierania archiwum: {result['archive_error']}")

    print(f"[{today}] {station_name}: dopisano {result['n_forecast_added']} wierszy prognozy "
          f"+ {result['n_archive_added']} wierszy archiwum")

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


if __name__ == "__main__":
    sys.exit(main())
