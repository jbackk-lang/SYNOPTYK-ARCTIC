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

    @property
    def hemisphere(self) -> str:
        """"N"/"S" liczone WPROST z `lat` (nie osobne, ręcznie wpisywane
        pole) - jedno źródło prawdy, nie da się przypadkiem rozjechać przy
        dodawaniu nowej stacji (patrz `STATIONS_NORTH`/`STATIONS_SOUTH`
        niżej, grupowanie w dropdownie dashboardu)."""
        return "S" if self.lat < 0 else "N"


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

# ── Pozostałe stacje (dodane 2026-08-31, na wyraźną prośbę użytkownika:
# "stacje arktyczne 3-5 najważniejszych" + "i polska na wyspie") ──
#
# W odróżnieniu od LONGYEARBYEN, `grid_elevation_m`/`grid_lat`/`grid_lon`
# poniżej są None - nie zweryfikowane jeszcze na żywym zapytaniu do
# Open-Meteo (patrz docstring ArcticStation wyżej: te pola wypełnia się
# DOPIERO po pierwszym realnym fetchu, żeby nie zgadywać). Współrzędne i
# `declared_altitude_m` pochodzą z publicznych źródeł (Wikipedia/NOAA GML/
# strony instytucji), zweryfikowane wyszukiwaniem 2026-08-31 - nie z
# pomiaru w tym repo.

# Polska Stacja Polarna Hornsund im. Stanisława Siedleckiego (IGF PAN) -
# jedyna POLSKA całoroczna stacja badawcza w Arktyce, południowy
# Spitsbergen (fiord Hornsund). φ=N77.00, λ=E15.5, 7 m n.p.m.
HORNSUND = ArcticStation(
    name="Hornsund_Polska_Stacja_Polarna",
    lat=77.00,
    lon=15.5,
    declared_altitude_m=7.0,
)

# Ny-Ålesund, Svalbard - najdalej na północ wysunięta stała osada
# badawcza na świecie (~79°N), wielonarodowe konsorcjum stacji
# (m.in. AWI, CNR, NPI) na tej samej wyspie co Longyearbyen/Hornsund -
# dobry punkt porównawczy w obrębie jednego archipelagu.
NY_ALESUND = ArcticStation(
    name="Ny_Alesund_Svalbard",
    lat=78.92500,
    lon=11.92222,
    declared_altitude_m=15.0,
)

# Alert, Nunavut (Kanada) - najbardziej na północ wysunięta stale
# zamieszkana osada świata (82°30'N, Wyspa Ellesmere'a, 817 km od
# bieguna północnego) - baza wojskowa CFS Alert + stacja WMO/GAW.
ALERT = ArcticStation(
    name="Alert_Nunavut_Kanada",
    lat=82.49917,
    lon=-62.34583,
    declared_altitude_m=30.0,
)

# Utqiagvik (dawniej Barrow), Alaska (USA) - najbardziej na północ
# wysunięte miasto USA, kluczowa amerykańska stacja klimatyczna NOAA
# (Barrow Atmospheric Baseline Observatory).
UTQIAGVIK = ArcticStation(
    name="Utqiagvik_Alaska",
    lat=71.29056,
    lon=-156.78861,
    declared_altitude_m=3.0,
)

# Tiksi, Republika Sacha (Jakucja), Rosja - ważna arktyczna stacja
# meteorologiczna nad Morzem Łaptiewów, wschodnia Syberia Arktyczna,
# ujście Leny.
TIKSI = ArcticStation(
    name="Tiksi_Rosja",
    lat=71.650,
    lon=128.867,
    declared_altitude_m=10.0,
)

# Polska Stacja Antarktyczna im. Henryka Arctowskiego (IBB PAN), Wyspa
# Króla Jerzego, Szetlandy Południowe - UWAGA: to ANTARKTYDA, przeciwna
# półkula względem reszty tego modułu (SYNOPTYK-ARCTIC = Arktyka).
# Dodana świadomie na wyraźną prośbę użytkownika ("i polska na wyspie" +
# potwierdzenie linkiem do arctowski.aq), NIE przez pomyłkę nazewniczą -
# druga (obok Hornsund) polska całoroczna stacja polarna, więc naturalnie
# pasuje do porównania "polskie stacje polarne", mimo że łamie założenie
# "Arktyka" z nazwy projektu. Sezony są tu ODWRÓCONE względem reszty
# stacji (antarktyczne lato = grudzień-luty) - "noc polarna
# listopad-luty" z README/HISTORIA_BUDOWY dotyczy PÓŁKULI PÓŁNOCNEJ i
# NIE ma zastosowania do tej jednej stacji.
ARCTOWSKI = ArcticStation(
    name="Arctowski_Antarktyda",
    lat=-62.160140,
    lon=-58.473247,
    declared_altitude_m=2.0,
)

# ── Pozostałe stacje półkuli południowej (dodane 2026-08-31, na pytanie
# "czy sa inne stacje oprocz arctowskiego" - tak, dolozone 3 kolejne
# uznane/znane stacje antarktyczne) ──

# McMurdo Station (USA) - największa stacja badawcza na Antarktydzie,
# Wyspa Rossa, obsługiwana przez United States Antarctic Program.
MCMURDO = ArcticStation(
    name="McMurdo_Antarktyda",
    lat=-77.846323,
    lon=166.668235,
    declared_altitude_m=10.0,
)

# Amundsen-Scott South Pole Station (USA) - DOKŁADNIE na biegunie
# południowym (90°S) - długość geograficzna jest tam matematycznie
# nieokreślona (wszystkie południki się zbiegają), przyjęto
# konwencjonalne 0°E (tak samo jak większość źródeł, patrz Wikipedia).
SOUTH_POLE = ArcticStation(
    name="Amundsen_Scott_Biegun_Poludniowy",
    lat=-90.0,
    lon=0.0,
    declared_altitude_m=2835.0,
)

# Stacja Wostok (Rosja) - wnętrze Antarktydy Wschodniej, miejsce
# zarejestrowania najniższej temperatury na Ziemi (-89.2°C, 1983).
VOSTOK = ArcticStation(
    name="Wostok_Antarktyda",
    lat=-78.464422,
    lon=106.837328,
    declared_altitude_m=3488.0,
)

STATIONS = [
    LONGYEARBYEN, HORNSUND, NY_ALESUND, ALERT, UTQIAGVIK, TIKSI,
    ARCTOWSKI, MCMURDO, SOUTH_POLE, VOSTOK,
]
STATIONS_BY_NAME = {s.name: s for s in STATIONS}
# Grupowanie po półkuli - uzywane przez webapp/app.py (GET /api/stations)
# do zbudowania dwoch optgroup w dropdownie dashboardu (Polnoc/Poludnie).
# Liczone z `hemisphere` (patrz property na ArcticStation), nie osobna
# reczna lista - dodanie nowej stacji do STATIONS automatycznie trafia
# do wlasciwej grupy przez sam znak `lat`.
STATIONS_NORTH = [s for s in STATIONS if s.hemisphere == "N"]
STATIONS_SOUTH = [s for s in STATIONS if s.hemisphere == "S"]
