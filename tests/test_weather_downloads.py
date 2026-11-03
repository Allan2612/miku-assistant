"""Weather (Open-Meteo answers faked, no internet) and "avísame cuando termine la descarga" (temp folder).

Run: core\\.venv\\Scripts\\python.exe -m tests.test_weather_downloads  (or with pytest)
"""

import tempfile
import time
import urllib.parse
from pathlib import Path

import core.tools.downloads as downloads
import core.tools.weather as weather

GEOCODE = {"results": [
    {"name": "San José", "country": "Estados Unidos", "country_code": "US", "latitude": 37.3, "longitude": -121.9},
    {"name": "San José", "country": "Costa Rica", "country_code": "CR", "latitude": 9.93, "longitude": -84.08},
]}
FORECAST = {
    "current": {"temperature_2m": 23.6, "weather_code": 3},
    "daily": {"weather_code": [61, 0], "temperature_2m_max": [26.4, 28.0], "temperature_2m_min": [17.2, 18.9],
              "precipitation_probability_max": [80, 5]},
}


def test_weather():
    asked = []

    def fake_get(url):
        asked.append(url)
        return GEOCODE if url.startswith(weather.GEOCODE_URL) else FORECAST

    weather._get = fake_get
    weather._PLACES.clear()
    res = weather.weather()
    assert res["result"] == ("Ahora hace 24 grados, nublado. Hoy, entre 17 y 26 grados, con 80 por ciento de "
                             "probabilidad de lluvia."), res
    query = urllib.parse.parse_qs(urllib.parse.urlparse(asked[-1]).query)
    assert query["latitude"] == ["9.93"], "the San José of the configured country, not the first one"
    res = weather.weather("mañana")
    assert res["result"] == "Mañana estará despejado, entre 19 y 28 grados, con 5 por ciento de probabilidad de lluvia."
    assert len([u for u in asked if u.startswith(weather.GEOCODE_URL)]) == 1, "the city is looked up once"

    weather._get = lambda url: {"results": []} if url.startswith(weather.GEOCODE_URL) else FORECAST
    assert weather.weather(city="Nolugar")["result"] == "No encontré la ciudad 'Nolugar'."

    def offline(url):
        raise OSError("no internet")

    weather._get = offline
    weather._PLACES.clear()
    assert not weather.weather()["ok"]


def test_download_finishes_or_is_cancelled():
    heard = []
    downloads.announce = heard.append
    downloads.DOWNLOADS = Path(tempfile.mkdtemp())
    downloads.POLL_S = 0.05
    assert "No veo ninguna descarga" in downloads.watch_downloads()["result"]

    game = downloads.DOWNLOADS / "juego.zip.opdownload"
    video = downloads.DOWNLOADS / "video.mp4.crdownload"
    game.write_bytes(b"x")
    video.write_bytes(b"x")
    res = downloads.watch_downloads()
    assert res["ok"] and "juego.zip" in res["result"] and "video.mp4" in res["result"], res
    assert downloads.watch_downloads()["ok"], "asking twice does not watch twice"

    game.rename(downloads.DOWNLOADS / "juego.zip")  # finished
    video.unlink()  # cancelled
    for _ in range(100):
        if len(heard) >= 2:
            break
        time.sleep(0.05)
    time.sleep(0.2)
    assert sorted(heard) == ["La descarga de video.mp4 se canceló.", "¡Terminó la descarga de juego.zip!"], heard


if __name__ == "__main__":
    test_weather()
    test_download_finishes_or_is_cancelled()
    print("ok")
