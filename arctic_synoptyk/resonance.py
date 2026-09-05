"""
resonance.py — sygnal 'rezonans' (TIMDR) jako PROXY liczony na realnych
danych z arctic_forecast_snapshots.csv (source == "archiwum_openmeteo"),
tym samym mechanizmem co w synoptyk-v2.0 (siostrzane repo, Krakow):
analyzer/timdr_analyzer.py (`len(anomalies_today) >= K`) i
forecaster/resonance_calibration.py (`_flag_resonance_days`).

PROXY, nie 1:1 port: ten CSV (patrz arctic_synoptyk/snapshots.py:FIELDNAMES)
nie ma godzinowych kanalow, ktorych chcialby prawdziwy TIMDRAnalyzer.analyze()
(datetime/temp/pressure/humidity/wind_speed/precip) - ma tylko DOBOWE
temp_min/avg/max_c, pressure_hpa, precip_mm, wind_kmh. Tak samo jak w
Krakowie, rezonans jest tu rekonstruowany jako PROXY: dla kazdej daty z
realnym pomiarem liczymy, ile z DOSTEPNYCH kanalow jest anomalnych wzgledem
mean +/- 2*std calego okna - dokladnie ta sama definicja "anomalii", co
domyslna galaz AdaptiveThresholds.get_thresholds() w Krakowie, gdy brak
klimatologii (mean±2*std). Traktowac jako przyblizenie zbudowane na
jedynych realnych danych, jakie w ogole mamy, nie jako podmiawke prawdziwego
TIMDRAnalyzer.analyze() (ktorego to repo w ogole nie ma).

ROZNICE wzgledem Krakowa (ten sam powod co w bias.py: inny schemat CSV):
  - kolumny kanalow to temp_max_c/pressure_hpa/precip_mm/wind_kmh (nie
    max_temp_c) - te same nazwy, ktorych juz uzywa arctic_synoptyk/bias.py;
  - brak wilgotnosci (tak samo jak w Krakowie - snapshoty jej nie loguja);
  - source jest DOKLADNYM stringiem "archiwum_openmeteo" (nie prefiksem
    jak Krakowskie IMGW_real_*/OpenMeteo_real_dailymax) - patrz
    snapshots.py naglowek.

Ten modul NIE uzywa pandas (to repo go nie ma w requirements.txt) - stdlib
`csv` + `statistics`, ten sam wybor stylu co bias.py.
"""
from __future__ import annotations

import csv
from statistics import mean, stdev

# Kanaly dostepne w arctic_forecast_snapshots.csv dla "rzeczywistosci"
# (source == "archiwum_openmeteo") - patrz arctic_synoptyk/snapshots.py:FIELDNAMES.
CHANNELS = ["temp_max_c", "pressure_hpa", "precip_mm", "wind_kmh"]

# Prog K sygnalu 'rezonans': dzien jest "rezonansowy", gdy >= K z dostepnych
# kanalow jest anomalnych (mean +/- 2*std calego okna kalibracji) tego
# samego dnia. Ta sama wartosc domyslna co w synoptyk-v2.0
# (analyzer/timdr_analyzer.py: DEFAULT_RESONANCE_K = 3) - nie znalezlismy
# tu wlasnego powodu, zeby liczyc inaczej: K=3 z 4 dostepnych kanalow to
# najnizszy prog, ktory nadal wymaga WSPOLWYSTAPIENIA wiekszosci kanalow
# (nie zapala sie na pojedynczym niezaleznym szumie pomiaru jednego
# kanalu). `resonance_calibration.calibrate_resonance()` moze go per
# stacja skorygowac (`recommended_k`) na podstawie realnych danych.
DEFAULT_K = 3

# Statistics.stdev (probka, ddof=1 - ten sam wariant co pandas .std()
# uzywane w Krakowskim resonance_calibration.py) wymaga >= 2 punktow;
# przyjmujemy >=3, zeby odchylenie nie bylo liczone na skrajnie malej
# probce (2 punkty daja "std", ktore nie mowi nic sensownego o "normie").
MIN_POINTS_FOR_STATS = 3


def load_real_channel_rows(csv_path: str, station: str) -> dict[str, dict[str, float]]:
    """Zwraca {target_date: {channel: wartosc}} na podstawie wierszy tej
    stacji z source == "archiwum_openmeteo". Jeden wpis na target_date -
    gdy jest wiecej niz jeden wiersz danej daty (nie powinno sie zdarzyc
    przy idempotentnym append_snapshot(), ale nie zakladamy tego tutaj),
    bierzemy OSTATNI zapisany w pliku - ten sam wybor co
    bias._load_pairs()/real_by_date. Brakujace/puste pola kanalu sa
    pomijane (nie 0.0) - kazdy kanal jest filtrowany niezaleznie, wiec
    stacja z np. brakujacym precip_mm w czesci wierszy wciaz dostaje
    sensowne progi dla pozostalych kanalow."""
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return {}

    out: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("station") != station or r.get("source") != "archiwum_openmeteo":
            continue
        target_date = r.get("target_date")
        if not target_date:
            continue
        values: dict[str, float] = {}
        for ch in CHANNELS:
            v = r.get(ch)
            if v in (None, ""):
                continue
            try:
                values[ch] = float(v)
            except ValueError:
                continue
        out[target_date] = values  # ostatni wiersz danej daty nadpisuje poprzedni
    return out


def _channel_series(real_by_date: dict[str, dict[str, float]], channel: str) -> dict[str, float]:
    return {d: vals[channel] for d, vals in real_by_date.items() if channel in vals}


def flag_resonance_days(real_by_date: dict[str, dict[str, float]], k: int = DEFAULT_K) -> dict[str, bool]:
    """PROXY rezonansu na danych dobowych - patrz docstring modulu. Zwraca
    {target_date: bool} dla kazdej daty obecnej w `real_by_date`: dzien
    jest rezonansowy, gdy >= k z DOSTEPNYCH tego dnia kanalow jest
    anomalnych wzgledem mean +/- 2*std calego okna `real_by_date` (progi
    liczone RAZ per kanal na calym oknie, nie per dzien - tak samo jak w
    Krakowie). Pusty dict, gdy `real_by_date` jest pusty."""
    if not real_by_date:
        return {}

    thresholds: dict[str, tuple[float, float]] = {}
    for ch in CHANNELS:
        series = _channel_series(real_by_date, ch)
        if len(series) < MIN_POINTS_FOR_STATS:
            continue
        vals = list(series.values())
        m = mean(vals)
        s = stdev(vals)
        if s == 0:
            continue
        thresholds[ch] = (m - 2 * s, m + 2 * s)

    result: dict[str, bool] = {}
    for target_date, values in real_by_date.items():
        anomaly_count = 0
        for ch, (low, high) in thresholds.items():
            v = values.get(ch)
            if v is None:
                continue
            if v < low or v > high:
                anomaly_count += 1
        result[target_date] = anomaly_count >= k
    return result
