"""
fetch_arctic_test.py — samodzielny skrypt do uruchomienia LOKALNIE (nie w
sandboksie Claude), bo sandbox ma zablokowany dostep do api.open-meteo.com
w swoim proxy (403 blocked-by-allowlist).

Uzycie:
    python fetch_arctic_test.py

Pobiera prognoze (7 dni) i archiwum (ostatnie 10 dni) dla Longyearbyen,
Svalbard (78.2232 N, 15.6267 E) - najbardziej znanej stacji/miejscowosci
arktycznej z realnymi, publicznie dostepnymi danymi Open-Meteo (model
ECMWF/ICON global z tego regionu).

Zapisuje wyniki do dwoch plikow JSON w tym samym folderze:
    arctic_forecast_result.json
    arctic_archive_result.json

Zadna z tych nazw stacji/wspolrzednych nie jest jeszcze wpisana do
zadnego kodu w tym repo - to tylko test, czy w ogole da sie stamtad
cokolwiek pobrac i jak wyglada odpowiedz (jednostki, brakujace pola,
NaN-y w okresie polarnej nocy itp.), zanim zaprojektuje sie na tym
cala logike stacji.
"""
import json
import urllib.request
import urllib.error

LAT, LON = 78.2232, 15.6267
STATION_NAME = "Longyearbyen_Svalbard"

FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "wind_speed_10m_max,pressure_msl_mean"
    "&forecast_days=7&timezone=UTC"
)

ARCHIVE_URL = (
    "https://archive-api.open-meteo.com/v1/archive"
    f"?latitude={LAT}&longitude={LON}"
    "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "wind_speed_10m_max,pressure_msl_mean"
    "&past_days=10&timezone=UTC"
)


def fetch(url: str, label: str, out_path: str) -> None:
    print(f"--- {label} ---")
    print(f"URL: {url}")
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            code = resp.status
            data = resp.read()
    except urllib.error.HTTPError as e:
        print(f"HTTP error: {e.code} {e.reason}")
        print(e.read().decode(errors='replace')[:500])
        return
    except urllib.error.URLError as e:
        print(f"Blad polaczenia: {e.reason}")
        return

    print(f"HTTP {code}, {len(data)} bajtow odpowiedzi")
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        print("Odpowiedz nie jest poprawnym JSON-em:")
        print(data[:500])
        return

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    print(f"Zapisano do {out_path}")

    daily = parsed.get("daily", {})
    print("Klucze w 'daily':", list(daily.keys()))
    if "time" in daily:
        print("Liczba dni:", len(daily["time"]))
        print("Pierwszy dzien:", daily["time"][0] if daily["time"] else None)
        print("Ostatni dzien:", daily["time"][-1] if daily["time"] else None)
    print()


if __name__ == "__main__":
    print(f"Stacja: {STATION_NAME} ({LAT}, {LON})\n")
    fetch(FORECAST_URL, "PROGNOZA (7 dni)", "arctic_forecast_result.json")
    fetch(ARCHIVE_URL, "ARCHIWUM (ostatnie 10 dni)", "arctic_archive_result.json")
    print("Gotowe. Wklej/przeslij oba pliki JSON z powrotem do analizy.")
