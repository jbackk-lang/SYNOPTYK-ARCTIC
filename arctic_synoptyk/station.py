"""
station.py — metadane stacji arktycznej/zdalnej.

W odróżnieniu od `synoptyk-v2.0/main_api.py::TOPOGRAPHY_DB` (miasta PL/EU,
każde ze stałą UHI wpisaną ręcznie), stacje w tym module NIE mają pola
`uhi` w ogóle - "miejska wyspa ciepła" nie ma zastosowania do zdalnej/
polarnej lokalizacji bez zabudowy miejskiej. Jedyna korekta temperaturowa,
jaka ma tu sens, to gradient wysokości (lapse rate) - i tylko jeśli
rzeczywista wysokość czujnika różni się od tego, co model przypisał
najbliższemu punktowi siatki.

Znany, udokumentowany problem, którego TU celowo unikamy: w
`topomap_data.py` (Synoptyk-v2.0) nieznana nazwa stacji dostaje CICHY
fallback `lat=52.0, lon=19.0` (środek Polski) - katastrofalne dla
lokalizacji arktycznej. Tu nie ma żadnego fallbacku - brak zdefiniowanej
stacji to błąd jawny (KeyError/ValueError), nie cichy zły wynik.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArcticStation:
    name: str
    lat: float
    lon: float
    # Wysokość deklarowana (np. z metadanych stacji/lotniska) - może różnić
    # się od tego, co faktycznie zwróci Open-Meteo dla najbliższego punktu
    # siatki (patrz `grid_elevation_m`, wypełniane po pierwszym fetchu).
    declared_altitude_m: float | None = None
    # Wypełniane dopiero po realnym zapytaniu do API (patrz fetch.py) -
    # Open-Meteo zwraca wysokość SWOJEGO punktu siatki, nie stacji.
    grid_elevation_m: float | None = None
    grid_lat: float | None = None
    grid_lon: float | None = None


# Longyearbyen, Svalbard - jedyna stacja tego modułu zweryfikowana na
# realnych danych (2026-08-26, patrz tests/fixtures/*.json). Współrzędne
# żądane vs zwrócone przez Open-Meteo (przyciągnięcie do punktu siatki
# modelu ECMWF/ICON, nie błąd):
#   żądane:   lat=78.2232,  lon=15.6267
#   zwrócone: lat=78.20738, lon=15.697675, elevation=26.0 m
# Różnica (~1.6 km) jest normalna dla modelu siatkowego globalnego -
# rozdzielczość rzędu kilku-kilkunastu km w tym regionie.
LONGYEARBYEN = ArcticStation(
    name="Longyearbyen_Svalbard",
    lat=78.2232,
    lon=15.6267,
    declared_altitude_m=28.0,  # wysokość lotniska Svalbard (referencyjna, nie z API)
    grid_elevation_m=26.0,
    grid_lat=78.20738,
    grid_lon=15.697675,
)
