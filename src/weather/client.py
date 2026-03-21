from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.weather.cities import City, TRISTATE_CITIES
from src.weather.models import WeatherReading

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openweathermap.org/data/2.5"
_REQUEST_DELAY_SEC = 0.12  # ~8 req/s, well under free tier limit of 60/min


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


class WeatherClient:
    def __init__(self, api_key: str, units: str = "imperial"):
        self.api_key = api_key
        self.units = units
        self._session = _build_session()

    def fetch_current(self, city: City) -> WeatherReading | None:
        params: dict[str, Any] = {
            "lat": city.lat,
            "lon": city.lon,
            "appid": self.api_key,
            "units": self.units,
        }
        fetched_at = datetime.now(timezone.utc)
        try:
            resp = self._session.get(f"{BASE_URL}/weather", params=params, timeout=10)
            resp.raise_for_status()
            return WeatherReading.from_api_response(resp.json(), city.name, city.state, fetched_at)
        except requests.HTTPError as exc:
            logger.error("HTTP error fetching %s %s: %s", city.name, city.state, exc)
        except requests.RequestException as exc:
            logger.error("Request error fetching %s %s: %s", city.name, city.state, exc)
        return None

    def fetch_all_tristate(
        self,
        cities: list[City] | None = None,
        request_delay: float = _REQUEST_DELAY_SEC,
    ) -> list[WeatherReading]:
        cities = cities or TRISTATE_CITIES
        results: list[WeatherReading] = []
        for city in cities:
            reading = self.fetch_current(city)
            if reading:
                results.append(reading)
                logger.info("Fetched weather for %s, %s: %.1f°F", city.name, city.state, reading.temp_f)
            else:
                logger.warning("Skipping %s, %s — no data returned", city.name, city.state)
            time.sleep(request_delay)
        logger.info("Fetched %d/%d cities successfully", len(results), len(cities))
        return results
