import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from arctic_synoptyk.station import ArcticStation, LONGYEARBYEN


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
