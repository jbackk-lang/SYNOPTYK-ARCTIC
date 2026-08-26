"""
backtest_real.py — URUCHOMIĆ NA LAPTOPIE (nie w sandboksie — zarówno
`previous-runs-api.open-meteo.com` jak i `archive-api.open-meteo.com` są
zablokowane w środowisku deweloperskim, patrz README).

Pobiera PRAWDZIWĄ historię: co prognoza Open-Meteo przewidywała N dni
wcześniej (Previous Runs API) vs co faktycznie się wydarzyło (Archive
API — ta sama reanaliza co używana w `run_arctic.py`/`bias.py`). Liczy
bias/MAE per lead_days na gotowym, historycznym oknie (domyślnie 90 dni)
zamiast czekać tygodniami na codzienne zbieranie przez `run_arctic.py`.

Zweryfikowane na prawdziwej odpowiedzi API 2026-08-27 (90 dni,
Longyearbyen) - zadzialalo bez poprawek, wynik w README ("Etap 4").
Jesli mimo to dostaniesz blad KeyError albo same puste wyniki, to znak,
ze ksztalt odpowiedzi Open-Meteo sie zmienil od tego czasu - zglos, co
dokladnie zwrocilo API.

Użycie:
    python backtest_real.py [liczba_dni]
    python backtest_real.py 90        # domyślnie
    python backtest_real.py 180
"""
import sys

from arctic_synoptyk.station import LONGYEARBYEN
from arctic_synoptyk.fetch import fetch_archive
from arctic_synoptyk.previous_runs import fetch_previous_runs, daily_max_by_lead, backtest_bias

DEFAULT_PAST_DAYS = 90


def main():
    past_days = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PAST_DAYS
    station = LONGYEARBYEN

    print(f"=== Backtest REALNY (Previous Runs API + Archive API), {station.name}, {past_days} dni ===\n")

    print(f"[1/2] Pobieram Previous Runs API (prognozy sprzed czasu, lead_days 1-7)...")
    try:
        payload = fetch_previous_runs(station, past_days=past_days)
        by_lead = daily_max_by_lead(payload)
    except Exception as e:
        print(f"BLAD pobierania/parsowania Previous Runs API: {e}")
        print("To realny sygnal, ze cos w ksztalcie odpowiedzi API sie nie zgadza "
              "z zalozeniami w previous_runs.py - zglosic, nie ignorowac.")
        return 1

    print(f"[2/2] Pobieram Archive API (rzeczywistosc)...")
    try:
        archive_rows = fetch_archive(station, past_days=past_days, exclude_trailing_days=2)
    except Exception as e:
        print(f"BLAD pobierania Archive API: {e}")
        return 1
    real_by_date = {r["date"]: r["temp_max_c"] for r in archive_rows if r["temp_max_c"] is not None}

    result = backtest_bias(by_lead, real_by_date, min_samples=5)

    print(f"\nWynik (n = liczba sparowanych dni, PRAWDZIWE dane, nie symulacja):\n")
    print(f"{'lead_days':>10} | {'n':>4} | {'bias °C':>8} | {'MAE °C':>7}")
    print("-" * 40)
    for lead in range(1, 8):
        if lead in result:
            e = result[lead]
            print(f"{lead:>10} | {e['n']:>4} | {e['bias']:>+8.2f} | {e['mae']:>7.2f}")
        else:
            n_raw = len(set(by_lead.get(lead, {})) & set(real_by_date))
            print(f"{lead:>10} | {n_raw:>4} | {'--':>8} | {'--':>7}  (za malo par, min. 5)")

    if not result:
        print("\nBrak zadnego wyniku - sprawdz komunikaty bledow powyzej / "
              "zglosic ksztalt odpowiedzi API.")
    else:
        print(f"\nTo PRAWDZIWY wynik z {past_days} dni historii Open-Meteo dla "
              f"{station.name} - ale wciaz jedna lokalizacja/okno czasowe, "
              "nie dowod ogolnej trafnosci na przyszlosc.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
