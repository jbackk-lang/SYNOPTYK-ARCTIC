"""
demo_synthetic_fill.py — DEMO: pokazuje, jak wyglada wyjscie compute_lead_bias(),
gdy juz jest wystarczajaco danych, na SYNTETYCZNYCH (wymyslonych, losowych)
danych - NIE na prawdziwym pomiarze stacji arktycznej.

PO CO TEN PLIK ISTNIEJE: zebranie realnych danych (run_arctic.py codziennie
przez ~2 tygodnie) wymaga czasu. Ten skrypt demonstruje MECHANIZM (ten sam
kod co bias.py/compute_lead_bias, ktory zadziala na prawdziwych danych),
zeby widziec ksztalt wyniku juz teraz - nie po to, zeby cokolwiek twierdzic
o rzeczywistej trafnosci Longyearbyen.

Pisze do OSOBNEGO pliku (`demo_synthetic_arctic_snapshots.csv`), NIGDY do
`arctic_forecast_snapshots.csv` (tam jest prawdziwy, zaseedowany wpis z
2026-08-26 - zanieczyszczenie go danymi zmyslonymi zepsuloby przyszly
prawdziwy pomiar). Kazdy wiersz i kazdy wydruk z tego skryptu jest jawnie
podpisany "DEMO/SYNTETYCZNE".

WAZNE (bug znaleziony i naprawiony przy pierwszym uruchomieniu): kazdy
kalendarzowy target_date ma DOKLADNIE JEDNA prawdziwa temperature w
rzeczywistosci, niezaleznie od tego, z ktorego dnia/lead_days ja
prognozujemy. Pierwsza wersja tego skryptu losowala nowa "rzeczywistosc"
dla kazdej pary (issue_date, lead) z osobna, wiec ten sam target_date
dostawal wiele SPRZECZNYCH wartosci "prawdy" - _load_pairs (patrz bias.py)
bierze ostatnia zapisana, wiec bias/MAE mieszaly sie miedzy lead_days i
zamierzony wzorzec (mniejszy blad na krotkim horyzoncie) w ogole nie byl
widoczny w wyniku. Naprawiono: najpierw generujemy JEDNA rzeczywista
temperature per target_date, potem dla kazdego (issue_date, lead) liczymy
prognoze wzgledem TEJ SAMEJ wartosci.
"""
import random
from datetime import date, timedelta

from arctic_synoptyk.snapshots import append_snapshot
from arctic_synoptyk.bias import compute_lead_bias

DEMO_CSV = "demo_synthetic_arctic_snapshots.csv"
STATION = "Longyearbyen_Svalbard_DEMO"

# Wymyslony wzorzec obciazenia - NIE zmierzony, tylko zeby demo mialo
# jakis niejednorodny ksztalt do pokazania (male niedoszacowanie na
# krotkim horyzoncie, rosnace przeszacowanie na dlugim - podobny
# JAKOSCIOWO do tego, co widzielismy dla Krakowa, ale te KONKRETNE
# liczby sa zmyslone, nie wyprowadzone z zadnego pomiaru).
def _synthetic_bias_for_lead(lead: int) -> float:
    return 1.2 - 0.35 * lead


def generate_demo_csv(n_days: int = 21, seed: int = 42) -> None:
    rng = random.Random(seed)
    start = date(2026, 8, 1)
    max_lead = 6

    # Krok 1: jedna "rzeczywista" temperatura per target_date, dla calego
    # zakresu dat, jakie moga wystapic jako cel prognozy (start..start+n_days-1+max_lead).
    real_temp_by_date: dict[date, float] = {}
    for offset in range(n_days + max_lead):
        d = start + timedelta(days=offset)
        # prosty sezonowy/losowy sygnal - wylacznie do demo, nie model klimatu
        real_temp_by_date[d] = round(4.0 + 3.0 * rng.random() + rng.gauss(0, 0.3), 2)

    written_real_dates: set[date] = set()

    for day_offset in range(n_days):
        issue = start + timedelta(days=day_offset)
        for lead in range(0, max_lead + 1):
            target = issue + timedelta(days=lead)
            real_temp = real_temp_by_date[target]
            true_bias = _synthetic_bias_for_lead(lead)
            forecast_temp = round(real_temp - true_bias + rng.gauss(0, 0.3), 1)

            fc_row = {
                "date": target.isoformat(), "temp_min_c": forecast_temp - 3,
                "temp_avg_c_approx": forecast_temp - 1.5, "temp_max_c": forecast_temp,
                "precip_mm": 0.0, "wind_kmh": 10.0, "pressure_hpa": 1010.0,
            }
            append_snapshot(DEMO_CSV, STATION, [fc_row], issue_date=issue, source="prognoza")

            if target not in written_real_dates:
                real_row = {
                    "date": target.isoformat(), "temp_min_c": real_temp - 3,
                    "temp_avg_c_approx": real_temp - 1.5, "temp_max_c": round(real_temp, 1),
                    "precip_mm": 0.0, "wind_kmh": 10.0, "pressure_hpa": 1010.0,
                }
                append_snapshot(DEMO_CSV, STATION, [real_row], issue_date=target, source="archiwum_openmeteo")
                written_real_dates.add(target)


if __name__ == "__main__":
    print("=== DEMO / DANE SYNTETYCZNE - NIE realny pomiar stacji arktycznej ===")
    generate_demo_csv()
    bias = compute_lead_bias(DEMO_CSV, STATION, min_samples=5)
    print(f"Wygenerowano {DEMO_CSV} (21 symulowanych dni x 7 lead_days).\n")
    print("Zamierzony (zmyslony) wzorzec: bias(lead) = 1.2 - 0.35*lead\n")
    print("Wynik compute_lead_bias() na danych SYNTETYCZNYCH (demo mechanizmu, nie pomiar):")
    for lead in sorted(bias):
        e = bias[lead]
        expected = _synthetic_bias_for_lead(lead)
        print(f"  lead_days={lead}: bias={e['bias']:+.2f} (zamierzone {expected:+.2f})  MAE={e['mae']:.2f}  n={e['n']}  [DEMO]")
