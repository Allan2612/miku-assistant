"""
Miku Assistant - Weather (tools/weather.py)

Open-Meteo: free, no API key, standard library only. The user's city comes from config.yaml ->
tools.weather_city ("Ciudad, País"); another city can be named. Each city is looked up once per session.
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import Any, Dict, Tuple

from core.config import load_config
from core.tools import tool

logger = logging.getLogger("miku.tools.weather")

TIMEOUT_S = 4.0
HOME_CITY = load_config().tools.weather_city
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search?"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast?"
_PLACES: Dict[str, Tuple[float, float, str]] = {}

# WMO weather codes, as said aloud
_SKY = {
    0: "despejado", 1: "casi despejado", 2: "parcialmente nublado", 3: "nublado", 45: "con niebla", 48: "con niebla",
    51: "con llovizna", 53: "con llovizna", 55: "con llovizna", 56: "con llovizna helada", 57: "con llovizna helada",
    61: "con lluvia ligera", 63: "con lluvia", 65: "con lluvia fuerte", 66: "con lluvia helada", 67: "con lluvia helada",
    71: "con nieve", 73: "con nieve", 75: "con nieve fuerte", 77: "con nieve", 80: "con chubascos",
    81: "con chubascos", 82: "con chubascos fuertes", 85: "con nieve", 86: "con nieve", 95: "con tormenta",
    96: "con tormenta y granizo", 99: "con tormenta y granizo",
}


def _get(url: str) -> Dict[str, Any]:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def _place(city: str) -> Tuple[float, float, str]:
    """(latitude, longitude, name) of "Ciudad" or "Ciudad, País". Raises LookupError if there is none."""
    key = city.strip().lower()
    if key not in _PLACES:
        name, _, country = (p.strip() for p in city.partition(","))
        results = _get(GEOCODE_URL + urllib.parse.urlencode({"name": name, "count": 10, "language": "es"}))
        found = results.get("results") or []
        in_country = [r for r in found if country and country.lower() in (str(r.get("country", "")).lower(),
                                                                           str(r.get("country_code", "")).lower())]
        if not (in_country or found):
            raise LookupError(city)
        best = (in_country or found)[0]
        _PLACES[key] = (best["latitude"], best["longitude"], best.get("name", name))
    return _PLACES[key]


@tool(
    name="weather",
    description=(
        "Dice el clima: ahora y hoy, o mañana (temperatura, cielo, probabilidad de lluvia). day: 'hoy' | 'mañana'. "
        "city: vacío = la ciudad del usuario; otra ciudad por su nombre ('Tokio', 'Madrid, España')."
    ),
)
def weather(day: str = "hoy", city: str = "") -> Dict[str, Any]:
    """Pronóstico de Open-Meteo para hoy o mañana."""
    tomorrow = day.strip().lower() in ("mañana", "manana", "tomorrow")
    try:
        lat, lon, name = _place(city or HOME_CITY)
        data = _get(FORECAST_URL + urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        }))
        daily = data["daily"]
        i = 1 if tomorrow else 0
        low, high = round(daily["temperature_2m_min"][i]), round(daily["temperature_2m_max"][i])
        rain = daily["precipitation_probability_max"][i]
        sky = _SKY.get(daily["weather_code"][i], "variable")
    except LookupError:
        return {"ok": False, "result": f"No encontré la ciudad '{city or HOME_CITY}'."}
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        logger.info("Weather failed: %s", e)
        return {"ok": False, "result": "No pude consultar el clima: no hay internet o el servicio no respondió."}
    where = f" en {name}" if city else ""
    rain_text = f", con {rain} por ciento de probabilidad de lluvia" if rain is not None else ""
    if tomorrow:
        return {"ok": True, "result": f"Mañana{where} estará {sky}, entre {low} y {high} grados{rain_text}."}
    now = data.get("current") or {}
    now_text = (f"Ahora{where} hace {round(now['temperature_2m'])} grados, "
                f"{_SKY.get(now.get('weather_code'), 'variable')}. " if "temperature_2m" in now else "")
    return {"ok": True, "result": f"{now_text}Hoy, entre {low} y {high} grados{rain_text}."}
