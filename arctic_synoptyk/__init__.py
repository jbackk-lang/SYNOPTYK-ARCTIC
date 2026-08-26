"""
arctic_synoptyk — wersja Synoptyka dla stacji arktycznej/zdalnej.

Etap 1 (ten pakiet): realna stacja arktyczna (Longyearbyen, Svalbard),
bez korekty UHI (nie ma zastosowania - to nie miasto), pobieranie i
logowanie tych samych danych co Synoptyk-v2.0 dla Krakowa, żeby po
kilku tygodniach dało się policzyć bias/MAE dokładnie tą samą metodą
(patrz `bias.py`).

Etap 2 (`offline.py`) - warstwa odporna na przerwy w łączności: bufor
lokalny, wskaźnik nieaktualności danych, symulowana przerwa satelitarna.

WAŻNE - co jest realne, a co jeszcze nie w tym pakiecie:
- `station.py`: współrzędne i wysokość ZWERYFIKOWANE 2026-08-26 przez
  realne zapytanie do Open-Meteo z laptopa użytkownika (sandbox Claude
  ma zablokowany dostęp do api.open-meteo.com w swoim proxy - patrz
  `tests/fixtures/*.json`, to są PRAWDZIWE odpowiedzi API, nie mocki).
- `fetch.py`: te same endpointy co w Synoptyk-v2.0 (Open-Meteo Forecast
  + Archive), ale na dobowym `daily=`, nie godzinowym `hourly=` jak w
  Krakowie - patrz zastrzeżenie w README o różnicy w liczeniu avg_temp_c.
- `bias.py`: identyczna logika jak `synoptyk-v2.0/forecaster/bias_correction.py`,
  wymaga TYGODNI zbieranych par (prognoza, rzeczywistość), żeby dać
  sensowny wynik - jedno pobranie z 2026-08-26 to dopiero pierwszy wiersz
  w CSV, NIE jest to jeszcze zmierzona trafność tej stacji. Krakowowi
  zebranie 1236 par zajęło tygodnie regularnego uruchamiania.
"""

from .station import ArcticStation, LONGYEARBYEN
from .offline import InstrumentReading, LocalBuffer, StalenessLevel, classify_staleness, degraded_forecast
from .connectivity_sim import connectivity_schedule, run_scenario

__all__ = [
    "ArcticStation", "LONGYEARBYEN",
    "InstrumentReading", "LocalBuffer", "StalenessLevel",
    "classify_staleness", "degraded_forecast",
    "connectivity_schedule", "run_scenario",
]
