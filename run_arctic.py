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


def main():
    today = date.today()
    station_name = STATION.name

    try:
        forecast_rows = fetch_forecast(STATION, forecast_days=7)
    except Exception as e:
        print(f"BLAD pobierania prognozy: {e}")
        forecast_rows = []

    try:
        archive_rows = fetch_archive(STATION, past_days=10)
    except Exception as e:
        print(f"BLAD pobierania archiwum: {e}")
        archive_rows = []

    n_fc = append_snapshot(CSV_PATH, station_name, forecast_rows, issue_date=today, source="prognoza")
    n_arch = append_snapshot(CSV_PATH, station_name, archive_rows, issue_date=today, source="archiwum_openmeteo")
    print(f"[{today}] {station_name}: dopisano {n_fc} wierszy prognozy + {n_arch} wierszy archiwum")

    bias = compute_lead_bias(CSV_PATH, station_name)
    if bias:
        print("Aktualna korekta obciazenia (lead_days -> bias/MAE/n):")
        for lead in sorted(bias):
            e = bias[lead]
            print(f"  lead_days={lead}: bias={e['bias']:+.2f} MAE={e['mae']:.2f} n={e['n']}")
    else:
        raw = compute_lead_bias(CSV_PATH, station_name, min_samples=1)
        print("Korekta jeszcze niedostepna - za malo sparowanych dni w CSV "
              "(potrzeba min. 5 par na dany lead_days, patrz README).")
        if raw:
            print("Dotychczasowy postep (surowe liczniki n, NIE wynik trafnosci):")
            for lead in sorted(raw):
                print(f"  lead_days={lead}: n={raw[lead]['n']} / 5")
        else:
            print("Jeszcze zero sparowanych dni (prognoza vs. pozniejsze archiwum "
                  "dla tej samej daty) - normalne w pierwszych ~2 dniach zbierania, "
                  "patrz README ('dlaczego archiwum wyklucza ostatnie 2 dni').")


if __name__ == "__main__":
    sys.exit(main())
