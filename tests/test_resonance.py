"""
test_resonance.py — testy arctic_synoptyk/resonance.py (proxy sygnalu
'rezonans' na danych dobowych). Testujemy funkcje bezposrednio na recznie
zbudowanych slownikach {target_date: {channel: wartosc}} (nie przez CSV -
to jest dla test_resonance_calibration.py) - konwencja "policzone na
kartce", zeby wynik dalo sie sprawdzic bez ufania samej implementacji.
"""
import os
import sys
import tempfile
from datetime import date
from statistics import mean, stdev

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.resonance import (
    CHANNELS,
    DEFAULT_K,
    flag_resonance_days,
    load_real_channel_rows,
)
from arctic_synoptyk.snapshots import append_snapshot


def test_flag_resonance_days_empty_input_returns_empty():
    assert flag_resonance_days({}) == {}


def test_flag_resonance_days_needs_at_least_k_anomalous_channels():
    # 8 dni "spokojnych" (wartosci blisko siebie na wszystkich kanalach) +
    # 1 dzien ze skokiem na WSZYSTKICH 4 kanalach jednoczesnie - powinien
    # zostac oflagowany jako rezonansowy (4 >= K=3 domyslne).
    real_by_date = {}
    for i in range(8):
        d = f"2026-08-{i+1:02d}"
        real_by_date[d] = {"temp_max_c": 5.0 + i * 0.1, "pressure_hpa": 1010.0 + i * 0.2,
                            "precip_mm": 0.0, "wind_kmh": 10.0 + i * 0.1}
    real_by_date["2026-08-20"] = {"temp_max_c": 80.0, "pressure_hpa": 700.0,
                                   "precip_mm": 200.0, "wind_kmh": 300.0}
    flags = flag_resonance_days(real_by_date, k=DEFAULT_K)
    assert flags["2026-08-20"] is True
    assert all(v is False for k, v in flags.items() if k != "2026-08-20")


def test_flag_resonance_days_single_anomalous_channel_below_k_is_not_resonant():
    # Tylko JEDEN kanal (wind_kmh) wychyla sie mocno na jednym dniu - ponizej
    # domyslnego K=3, wiec ten dzien NIE powinien byc oflagowany. Kanaly
    # "spokojne" maja tu CELOWO lekki naturalny jitter (nie stala wartosc)
    # - gdyby wszystkie 8 dni bazowych mialy identyczna wartosc, std
    # wychodziloby ~0 i NAWET male odchylenie (5.1 vs 5.0) wypadaloby poza
    # mean+/-2*std, falszywie oflagowane jako anomalia (regresja znaleziona
    # przy pisaniu tego testu - patrz test_flag_resonance_days_needs_at_least_k_anomalous_channels
    # po ten sam wzorzec jittera).
    real_by_date = {}
    for i in range(8):
        d = f"2026-08-{i+1:02d}"
        real_by_date[d] = {"temp_max_c": 5.0 + i * 0.1, "pressure_hpa": 1010.0 + i * 0.2,
                            "precip_mm": i * 0.05, "wind_kmh": 10.0 + i * 0.1}
    real_by_date["2026-08-20"] = {"temp_max_c": 5.1, "pressure_hpa": 1010.5,
                                   "precip_mm": 0.1, "wind_kmh": 300.0}
    flags = flag_resonance_days(real_by_date, k=DEFAULT_K)
    assert flags["2026-08-20"] is False


def test_flag_resonance_days_respects_custom_k():
    # Jitter na kanalach "spokojnych" (nie stala wartosc) - patrz komentarz
    # w test_flag_resonance_days_single_anomalous_channel_below_k_is_not_resonant
    # po wyjasnienie, dlaczego stala baza psuje test (std~0 -> falszywe
    # anomalie na nieistotnych kanalach).
    real_by_date = {}
    for i in range(8):
        d = f"2026-08-{i+1:02d}"
        real_by_date[d] = {"temp_max_c": 5.0 + i * 0.1, "pressure_hpa": 1010.0 + i * 0.2,
                            "precip_mm": i * 0.02, "wind_kmh": 10.0 + i * 0.05}
    # Dwa kanaly anomalne jednoczesnie (temp, pressure); precip/wind
    # kontynuuja naturalny jitter (nie sa anomalne).
    real_by_date["2026-08-20"] = {"temp_max_c": 80.0, "pressure_hpa": 700.0,
                                   "precip_mm": 0.1, "wind_kmh": 10.3}
    assert flag_resonance_days(real_by_date, k=3)["2026-08-20"] is False
    assert flag_resonance_days(real_by_date, k=2)["2026-08-20"] is True


def test_flag_resonance_days_missing_channel_values_are_skipped_not_zero():
    # Kanal calkowicie brakujacy dla wszystkich dni (np. stacja bez precip)
    # nie powinien powodowac wyjatku ani liczyc sie jako "0.0 - anomalia".
    real_by_date = {
        "2026-08-01": {"temp_max_c": 5.0, "pressure_hpa": 1010.0, "wind_kmh": 10.0},
        "2026-08-02": {"temp_max_c": 5.2, "pressure_hpa": 1009.0, "wind_kmh": 9.0},
        "2026-08-03": {"temp_max_c": 4.8, "pressure_hpa": 1011.0, "wind_kmh": 11.0},
    }
    flags = flag_resonance_days(real_by_date, k=DEFAULT_K)
    assert set(flags.keys()) == set(real_by_date.keys())


def test_load_real_channel_rows_filters_station_and_source():
    with tempfile.TemporaryDirectory() as d:
        csv_path = os.path.join(d, "arctic.csv")
        rec = {"date": "2026-08-27", "temp_min_c": 1.0, "temp_avg_c_approx": 2.0,
               "temp_max_c": 3.0, "precip_mm": 0.5, "wind_kmh": 8.0, "pressure_hpa": 1005.0}
        append_snapshot(csv_path, "StacjaA", [rec], issue_date=date(2026, 8, 27), source="archiwum_openmeteo")
        append_snapshot(csv_path, "StacjaA", [rec], issue_date=date(2026, 8, 26), source="prognoza")
        append_snapshot(csv_path, "StacjaB", [rec], issue_date=date(2026, 8, 27), source="archiwum_openmeteo")

        real = load_real_channel_rows(csv_path, "StacjaA")
        assert list(real.keys()) == ["2026-08-27"]
        assert real["2026-08-27"] == {"temp_max_c": 3.0, "pressure_hpa": 1005.0,
                                       "precip_mm": 0.5, "wind_kmh": 8.0}


def test_load_real_channel_rows_missing_file_returns_empty_dict():
    assert load_real_channel_rows("/nonexistent/path/does_not_exist.csv", "StacjaA") == {}


def test_channels_constant_has_no_humidity():
    # Ten CSV (arctic_synoptyk/snapshots.py:FIELDNAMES) nie loguje
    # wilgotnosci - regression test, zeby ktos przypadkiem jej tu nie dopisal.
    assert "humidity" not in CHANNELS
    assert set(CHANNELS) == {"temp_max_c", "pressure_hpa", "precip_mm", "wind_kmh"}


def _old_self_referential_flag(vals: list[float], idx: int) -> bool:
    """Odtwarza CELOWO stara (NAPRAWIONA) wersje flag_resonance_days:
    prog mean+/-2*std liczony na CALEJ probce, WLACZNIE z ocenianym
    punktem - uzywana ponizej WYLACZNIE jako punkt odniesienia w tescie
    regresyjnym na maskowanie, nie importowana z produkcyjnego kodu
    (ktorego juz nie ma - patrz resonance.py:flag_resonance_days)."""
    m = mean(vals)
    s = stdev(vals)
    v = vals[idx]
    return v < (m - 2 * s) or v > (m + 2 * s)


def test_flag_resonance_days_leave_one_out_avoids_masking_on_small_sample():
    # Realistyczny scenariusz dla tego repo (30-dniowa retencja CSV / 10
    # stacji - patrz docstring resonance_calibration.py): TYLKO 4 dni
    # bazowe + 1 dzien z duzym skokiem na wszystkich 4 kanalach. Stara
    # (samo-odnoszaca sie) wersja progu liczyla mean+/-2*std z WLASNEGO
    # udzialu tego skoku w probce - przy n=5 jeden ekstremalny punkt
    # potrafi sam zawyzyc wlasne std na tyle, ze NIGDY nie przekroczy
    # progu, NIEZALEZNIE od tego, jak duzy jest skok (patrz ponizsza
    # pętla po amplitudach - to jest dokladnie ten sam mechanizm
    # maskowania, co znaleziony i naprawiony w FLIGHT-TRACKING-TIMDR/
    # timdr_flight.py:twist_3d i opisany w GIA-TIMDR/docs/geometry/
    # TIMDR_Trefoil_RealDataValidation.md).
    base = {"temp_max_c": [5.0, 5.1, 4.9, 5.05],
            "pressure_hpa": [1010.0, 1010.5, 1009.5, 1010.2],
            "precip_mm": [0.0, 0.1, 0.05, 0.0],
            "wind_kmh": [10.0, 10.2, 9.8, 10.1]}
    for amplitude in (4, 6, 8, 12, 20):
        real_by_date = {}
        for i in range(4):
            d = f"2026-08-{i+1:02d}"
            real_by_date[d] = {ch: vals[i] for ch, vals in base.items()}
        real_by_date["2026-08-20"] = {ch: vals[0] * amplitude for ch, vals in base.items()}

        # Stara metoda: prog liczony na WSZYSTKICH 5 wartosciach danego
        # kanalu (z ocenianym dniem wlacznie) - masking check.
        old_anomalous = sum(
            1 for ch, vals in base.items()
            if _old_self_referential_flag(vals + [vals[0] * amplitude], 4)
        )
        assert old_anomalous < DEFAULT_K, (
            f"amplituda={amplitude}: oczekiwano, ze stara (samo-odnoszaca sie) metoda "
            f"NIE zauwazy anomalii (ponizej k={DEFAULT_K}) - to jest teza tego testu "
            f"(maskowanie), uzyskano {old_anomalous} anomalnych kanalow"
        )

        # Naprawiona metoda (flag_resonance_days, leave-one-out): powinna
        # wykryc rezonans NIEZALEZNIE od amplitudy w tym zakresie.
        flags = flag_resonance_days(real_by_date, k=DEFAULT_K)
        assert flags["2026-08-20"] is True, (
            f"amplituda={amplitude}: naprawiona (leave-one-out) metoda powinna wykryc "
            f"rezonans tam, gdzie stara go maskowala"
        )
