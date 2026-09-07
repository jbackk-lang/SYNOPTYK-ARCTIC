"""Jednorazowy skrypt: pokazuje status kalibracji rezonansu dla wszystkich
10 stacji na aktualnym arctic_forecast_snapshots.csv. Uruchom:

    python check_resonance_status.py
"""
from arctic_synoptyk.station import STATIONS
from arctic_synoptyk.resonance_calibration import calibrate_resonance

CSV_PATH = "arctic_forecast_snapshots.csv"

for station in STATIONS:
    result = calibrate_resonance(CSV_PATH, station.name)
    status = result["status"]
    if status == "calibrated":
        print(
            f"{station.name:35s} CALIBRATED  n_res={result['n_resonance_days']:3d} "
            f"n_normal={result['n_normal_days']:3d}  mae_res={result['mae_resonance']:.2f} "
            f"mae_normal={result['mae_normal']:.2f}  multiplier={result['confidence_multiplier']:.2f} "
            f"recommended_k={result['recommended_k']}"
        )
    else:
        print(
            f"{station.name:35s} insufficient_data  n_res={result['n_resonance_days']:3d} "
            f"n_normal={result['n_normal_days']:3d}  ({result['reason']})"
        )
