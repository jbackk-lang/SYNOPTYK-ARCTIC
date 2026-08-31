import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.station import (
    ArcticStation, LONGYEARBYEN, HORNSUND, NY_ALESUND, ALERT, UTQIAGVIK,
    TIKSI, ARCTOWSKI, MCMURDO, SOUTH_POLE, VOSTOK,
    STATIONS, STATIONS_BY_NAME, STATIONS_NORTH, STATIONS_SOUTH,
)


def test_longyearbyen_no_uhi_field():
    """Kluczowa roznica vs Synoptyk-v2.0 TOPOGRAPHY_DB: brak pola 'uhi' -
    sprawdzamy, ze dataclass go w ogole nie definiuje (nie: ze jest 0)."""
    assert not hasattr(LONGYEARBYEN, "uhi")


def test_longyearbyen_requested_vs_grid_coords_differ_but_close():
    """Zweryfikowane realnym zapytaniem 2026-08-26: Open-Meteo przyciaga do
    najblizszego punktu siatki, rozjazd powinien byc mały (<0.1 stopnia)."""
    assert LONGYEARBYEN.grid_lat is not None
    assert abs(LONGYEARBYEN.lat - LONGYEARBYEN.grid_lat) < 0.1
    assert abs(LONGYEARBYEN.lon - LONGYEARBYEN.grid_lon) < 0.1


def test_custom_station_without_grid_metadata_is_allowed():
    """Nowa stacja (przed pierwszym fetchem) nie musi jeszcze miec
    grid_elevation/grid_lat/grid_lon - te pola sa Optional celowo."""
    s = ArcticStation(name="Test_Station", lat=70.0, lon=20.0)
    assert s.grid_elevation_m is None
    assert s.grid_lat is None


def test_no_silent_default_for_missing_station():
    """W odroznieniu od topomap_data.py (Synoptyk-v2.0), ktore dla
    nieznanej nazwy cicho zwraca lat=52.0/lon=19.0 (srodek Polski) - tu
    nie ma zadnego mechanizmu 'lookup po nazwie z fallbackiem'. Sprawdzamy
    dwie rzeczy: (1) nie ma w module zadnej funkcji-lookupu po nazwie
    (np. get_station_by_name/find_station), (2) ArcticStation.lat/lon nie
    maja wartosci domyslnych - trzeba je podac jawnie przy KAZDEJ
    konstrukcji, wiec nie da sie przypadkiem dostac "cichej" stacji bez
    wspolrzednych."""
    import inspect
    from arctic_synoptyk import station as station_module

    names_in_module = [name for name, _ in inspect.getmembers(station_module)]
    assert not any("lookup" in n.lower() or "get_station" in n.lower() or "find_station" in n.lower()
                   for n in names_in_module), (
        "znaleziono funkcje-lookup po nazwie w station.py - to dokladnie "
        "mechanizm, ktory w topomap_data.py prowadzi do cichego fallbacku"
    )

    sig = inspect.signature(ArcticStation)
    assert sig.parameters["lat"].default is inspect.Parameter.empty
    assert sig.parameters["lon"].default is inspect.Parameter.empty


# ── Wiele stacji (dodane 2026-08-31) ────────────────────────────────────

def test_stations_list_has_ten_unique_entries():
    """Longyearbyen + 9 dodanych 2026-08-31: Hornsund, Ny-Alesund, Alert,
    Utqiagvik, Tiksi (polnoc) + Arctowski, McMurdo, Amundsen-Scott, Wostok
    (poludnie) - nazwy musza byc unikalne, bo `station` to klucz
    idempotentnosci w snapshots.py (patrz append_snapshot)."""
    assert len(STATIONS) == 10
    names = [s.name for s in STATIONS]
    assert len(names) == len(set(names)), "zduplikowana nazwa stacji zepsulaby idempotentnosc CSV"


def test_stations_by_name_matches_stations_list():
    assert set(STATIONS_BY_NAME) == {s.name for s in STATIONS}
    for s in STATIONS:
        assert STATIONS_BY_NAME[s.name] is s


def test_new_stations_have_no_uhi_field_either():
    """Ta sama zasada co dla LONGYEARBYEN (test wyzej) - zadna stacja
    zdalna/polarna w tym module nie ma UHI, niezaleznie od polkuli."""
    for s in (HORNSUND, NY_ALESUND, ALERT, UTQIAGVIK, TIKSI, ARCTOWSKI):
        assert not hasattr(s, "uhi")


def test_all_stations_have_plausible_coordinates():
    """Luzna kontrola sanity - szerokosc geograficzna w [-90, 90], dlugosc
    w [-180, 180], i stacje polnocne wysoko na polkuli polnocnej (>60N) -
    to jest modul 'arctic', wiec polnocna grupa ma byc faktycznie
    arktyczna. Poludniowa grupa (Antarktyda) sprawdzana osobno nizej -
    tam odwrotne kryterium (<-60)."""
    for s in STATIONS:
        assert -90.0 <= s.lat <= 90.0
        assert -180.0 <= s.lon <= 180.0
    assert all(s.lat > 60.0 for s in STATIONS_NORTH), (
        "wszystkie stacje polnocne powinny byc arktyczne (>60N)"
    )
    assert all(s.lat < -60.0 for s in STATIONS_SOUTH), (
        "wszystkie stacje poludniowe powinny byc antarktyczne (<-60N)"
    )


def test_southern_hemisphere_stations_are_the_deliberate_antarctic_exception():
    """4 stacje (Arctowski, McMurdo, Amundsen-Scott, Wostok) sa swiadomym
    wyjatkiem od nazwy modulu ('arctic') - dodane na wyrazna prosbe
    uzytkownika (najpierw Arctowski jako druga polska stacja polarna,
    potem dolozone 3 kolejne uznane stacje antarktyczne po pytaniu 'czy sa
    inne stacje oprocz arctowskiego'). Kazda ma ujemna szerokosc
    geograficzna i nalezy do STATIONS_SOUTH - i TYLKO one."""
    assert set(STATIONS_SOUTH) == {ARCTOWSKI, MCMURDO, SOUTH_POLE, VOSTOK}
    assert len(STATIONS_SOUTH) == 4
    for s in STATIONS_SOUTH:
        assert s.lat < 0, f"{s.name}: Antarktyda = polkula poludniowa, szerokosc ujemna"
        assert s.hemisphere == "S"
    for s in STATIONS_NORTH:
        assert s.hemisphere == "N"
    assert "Antarktyda" in ARCTOWSKI.name
