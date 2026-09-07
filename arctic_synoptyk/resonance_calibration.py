"""
resonance_calibration.py — domyka petle samokorekty sygnalu 'rezonans'
(TIMDR) tym samym mechanizmem, ktorym siostrzane repo (synoptyk-v2.0,
Krakow) domyka ja dla swojego glownego silnika prognozy: liczy NA ZYWO z
arctic_forecast_snapshots.csv (dokladnie tego samego pliku, co
arctic_synoptyk/bias.py), czy dni oflagowane jako "rezonansowe"
(arctic_synoptyk/resonance.py:flag_resonance_days, prog K) faktycznie
mialy wyzszy blad prognozy (MAE = |real - forecast|) niz dni bez rezonansu.

PO CO: gdyby ten sygnal byl kiedys wpiety do wlasnego silnika prognozy tego
repo (obecnie SYNOPTYK-ARCTIC go nie ma - nie ma tu odpowiednika
forecaster/timdr_forecast.py), zalozenie "rezonans -> wiekszy blad
prognozy -> powinien poszerzac niepewnosc" nigdy nie bylo sprawdzone na
realnych danych. Ten modul sprawdza to zalozenie i wyprowadza z niego
`confidence_multiplier` - do tej pory uzywany jedynie diagnostycznie przez
GET /api/resonance (patrz webapp/app.py), nie zasilajacy jeszcze zadnego
silnika prognozy w tym repo.

ADAPTACJA do tego repo (NIE 1:1 port - schemat CSV inny, patrz
arctic_synoptyk/snapshots.py):
  - kolumny: temp_max_c/pressure_hpa/precip_mm/wind_kmh (nie max_temp_c
    jak w Krakowie), brak wilgotnosci (tak samo jak w Krakowie);
  - source jest DOKLADNYM stringiem "prognoza"/"archiwum_openmeteo" (nie
    prefiksem jak Krakowskie IMGW_real_*/OpenMeteo_real_dailymax);
  - `station` jest tu WYMAGANYM argumentem pozycyjnym (tak jak w
    arctic_synoptyk/bias.py:compute_lead_bias) - to repo zawsze liczy per
    stacja (10 stacji, kazda z osobnym torem danych w tym samym CSV), w
    odroznieniu od Krakowa, gdzie `station=None` mialo sens (jedna stacja
    domyslna dzielaca caly plik);
  - jedna kolumna (`forecast_col`, domyslnie "temp_max_c") sluzy ZA OBA
    - i prognoze, i "rzeczywistosc" - bo w tym CSV wiersze "prognoza" i
    "archiwum_openmeteo" uzywaja tej samej nazwy kolumny (patrz bias.py -
    Krakow mial osobne `forecast_col`/`real_col`, bo Open-Meteo `daily=`
    tam nie dawalo prawdziwej sredniej, tu ten problem nie wystepuje w
    ten sam sposob, wiec podazamy za bias.py, nie duplikujemy dwoch
    parametrow bez powodu).

Parowanie prognoza<->rzeczywistosc powiela KONWENCJE z bias.py
(_load_pairs: source=="prognoza"/"archiwum_openmeteo", grupowanie po
target_date biorace OSTATNI wpis rzeczywisty danego dnia) - `_load_pairs_by_date()`
ponizej to CELOWO OSOBNA funkcja od `bias._load_pairs()`, bo TA potrzebuje
zachowac `target_date` (do polaczenia kazdej pary z flaga rezonansu tego
dnia), a `bias._load_pairs()` go odrzuca. Dokladnie ten sam powod, dla
ktorego Krakowski resonance_calibration.py ma wlasne `_load_pairs_by_date()`
zamiast wolac wprost `bias_correction._load_pairs()`.

UCZCIWOSC (identyczny wzorzec co bias.compute_lead_bias i co Krakowski
resonance_calibration.calibrate_resonance - patrz tam po pelny opis
"test bez mocy = brak wniosku, nie brak efektu", timdr-signal-framework):
gdy sparowanych dni jest za malo w KTOREJKOLWIEK z dwoch grup
(rezonans / brak rezonansu) wzgledem `min_samples_per_group`, kalibracja
NIE jest stosowana - `confidence_multiplier` zostaje 1.0 (identyczne
zachowanie jak bez kalibracji), `status` = "insufficient_data", z jawnym
powodem. Nigdy nie udajemy, ze kalibracja sie powiodla na garstce
przypadkow.

Ten fallback bedzie tu odpalal sie CZESCIEJ niz dla Krakowa: 10 stacji
dzieli uwage/limity API, a arctic_forecast_snapshots.csv ma tylko
30-dniowa retencje (patrz README) - malo ktora stacja ma w danym momencie
>= 2 * min_samples_per_group (domyslnie 16) sparowanych realnych dni
jednoczesnie. To oczekiwany, normalny stan wiekszosci stacji wiekszosc
czasu - nie blad tego modulu."""
from __future__ import annotations

import csv

from .resonance import DEFAULT_K, flag_resonance_days, load_real_channel_rows

# Brak korekty - dokladnie taki wplyw, jak przed wprowadzeniem kalibracji.
DEFAULT_CONFIDENCE_MULTIPLIER = 1.0


def _load_pairs_by_date(csv_path: str, station: str, forecast_col: str = "temp_max_c") -> list[dict]:
    """Jak `bias._load_pairs`, ale zachowuje `target_date` (potrzebne, zeby
    polaczyc kazda pare forecast/real z flaga rezonansu tego dnia) -
    powiela TE SAMA logike parowania (source=="prognoza"/"archiwum_openmeteo",
    ostatni wpis rzeczywisty na target_date wygrywa) - patrz bias.py po
    pelny opis konwencji/edge case'ow, ktore tu tez obowiazuja."""
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return []

    rows = [r for r in rows if r.get("station") == station]
    fc = [r for r in rows if r.get("source") == "prognoza"]
    real = [r for r in rows if r.get("source") == "archiwum_openmeteo"]

    real_by_date: dict[str, float] = {}
    for r in real:
        v = r.get(forecast_col)
        if v not in (None, ""):
            real_by_date[r["target_date"]] = float(v)

    pairs = []
    for r in fc:
        real_val = real_by_date.get(r["target_date"])
        fc_val = r.get(forecast_col)
        lead = r.get("lead_days")
        if real_val is None or fc_val in (None, "") or lead in (None, ""):
            continue
        pairs.append({
            "target_date": r["target_date"],
            "lead_days": int(float(lead)),
            "forecast": float(fc_val),
            "real": real_val,
        })
    return pairs


def _insufficient(k: int, n_res: int, n_normal: int, reason: str) -> dict:
    return {
        "status": "insufficient_data",
        "k": k,
        "recommended_k": k,
        "n_resonance_days": n_res,
        "n_normal_days": n_normal,
        "confidence_multiplier": DEFAULT_CONFIDENCE_MULTIPLIER,
        "reason": reason,
    }


def calibrate_resonance(
    csv_path: str,
    station: str,
    k: int = DEFAULT_K,
    min_samples_per_group: int = 8,
    forecast_col: str = "temp_max_c",
) -> dict:
    """
    Liczy, czy dni oflagowane jako rezonansowe (proxy
    `resonance.flag_resonance_days`, prog `k`) faktycznie mialy wyzszy
    blad prognozy (MAE = |real - forecast|) niz dni bez rezonansu, dla
    JEDNEJ stacji (`station` - wymagany, patrz docstring modulu), i z
    tego wyprowadza:

      - `confidence_multiplier`: stosunek mae_resonance/mae_normal,
        PODLOGOWANY do 1.0 (rezonans z definicji ma tylko poszerzac
        niepewnosc, nigdy jej nie zawezac ponizej poziomu bazowego) i
        SUFITOWANY do 3.0 (zeby jeden skrajny dzien nie zdominowal calej
        kalibracji).
      - `recommended_k`: sugerowana korekta progu K - +1 (surowszy prog,
        k<=5), gdy dni rezonansowe NIE sa w praktyce gorsze (ratio < 1.05,
        obecny K lapie glownie falszywe alarmy); -1 (luzniejszy prog,
        k>=2), gdy sa WYRAZNIE gorsze (ratio > 2.0); inaczej bez zmian.

    Zwraca dict z kluczem "status":
      "calibrated" - wystarczajaco danych w OBU grupach (>= min_samples_per_group
        sparowanych dni kazda) - zawiera tez mae_resonance/mae_normal/
        n_resonance_days/n_normal_days.
      "insufficient_data" - za malo sparowanych dni w ktorejs z grup
        (albo CSV brakuje/jest pusty/uszkodzony) - `confidence_multiplier`
        = 1.0 (brak korekty), `reason` z opisem. Nigdy nie rzuca wyjatku.
    """
    try:
        real_by_date = load_real_channel_rows(csv_path, station)
        pairs = _load_pairs_by_date(csv_path, station, forecast_col=forecast_col)
    except Exception as exc:  # brak pliku, uszkodzony CSV, zla kolumna...
        return _insufficient(k, 0, 0, f"blad wczytywania CSV ({exc!r})")

    if not real_by_date or not pairs:
        return _insufficient(k, 0, 0, "brak sparowanych danych prognoza+rzeczywistosc w CSV")

    resonance_flags = flag_resonance_days(real_by_date, k=k)

    errors_res: list[float] = []
    errors_normal: list[float] = []
    for p in pairs:
        err = abs(p["real"] - p["forecast"])
        if resonance_flags.get(p["target_date"], False):
            errors_res.append(err)
        else:
            errors_normal.append(err)

    n_res = len(errors_res)
    n_normal = len(errors_normal)

    if n_res < min_samples_per_group or n_normal < min_samples_per_group:
        return _insufficient(
            k, n_res, n_normal,
            f"za malo sparowanych dni w jednej z grup (rezonans={n_res}, "
            f"normalne={n_normal}), potrzeba >= {min_samples_per_group} w obu",
        )

    mae_resonance = sum(errors_res) / n_res
    mae_normal = sum(errors_normal) / n_normal
    ratio = (mae_resonance / mae_normal) if mae_normal > 0 else 1.0
    confidence_multiplier = min(3.0, max(1.0, ratio))

    recommended_k = k
    if ratio < 1.05 and k < 5:
        recommended_k = k + 1
    elif ratio > 2.0 and k > 2:
        recommended_k = k - 1

    return {
        "status": "calibrated",
        "k": k,
        "recommended_k": recommended_k,
        "n_resonance_days": n_res,
        "n_normal_days": n_normal,
        "mae_resonance": round(mae_resonance, 3),
        "mae_normal": round(mae_normal, 3),
        "confidence_multiplier": round(confidence_multiplier, 3),
    }


def get_resonance_confidence_multiplier(
    csv_path: str,
    station: str,
    k: int = DEFAULT_K,
    min_samples_per_group: int = 8,
    **kwargs,
) -> float:
    """Wygodny wrapper: zwraca WYLACZNIE mnoznik (1.0 = brak korekty - ani
    gdy dane sa niewystarczajace, ani przy jakimkolwiek bledzie). Nigdy
    nie rzuca wyjatku - bezpieczne do wstrzykniecia jako domyslny argument
    konstruktora ewentualnego przyszlego silnika prognozy tego repo."""
    try:
        result = calibrate_resonance(
            csv_path, station, k=k, min_samples_per_group=min_samples_per_group, **kwargs,
        )
        return result["confidence_multiplier"]
    except Exception:
        return DEFAULT_CONFIDENCE_MULTIPLIER
