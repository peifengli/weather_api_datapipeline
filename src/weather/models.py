from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class WeatherCondition:
    id: int
    main: str
    description: str
    icon: str


@dataclass
class WeatherReading:
    city: str
    state: str
    country: str
    lat: float
    lon: float
    fetched_at: datetime
    observed_at: datetime
    temp_f: float
    feels_like_f: float
    temp_min_f: float
    temp_max_f: float
    humidity_pct: int
    pressure_hpa: int
    visibility_m: int
    wind_speed_mph: float
    wind_deg: int
    wind_gust_mph: float | None
    clouds_pct: int
    condition: WeatherCondition
    sunrise: datetime
    sunset: datetime
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_api_response(
        cls,
        data: dict[str, Any],
        city: str,
        state: str,
        fetched_at: datetime | None = None,
    ) -> WeatherReading:
        if fetched_at is None:
            fetched_at = datetime.now(UTC)

        main = data["main"]
        wind = data.get("wind", {})
        weather = data["weather"][0]
        sys = data.get("sys", {})

        return cls(
            city=city,
            state=state,
            country=sys.get("country", "US"),
            lat=data["coord"]["lat"],
            lon=data["coord"]["lon"],
            fetched_at=fetched_at,
            observed_at=datetime.fromtimestamp(data["dt"], tz=UTC),
            temp_f=main["temp"],
            feels_like_f=main["feels_like"],
            temp_min_f=main["temp_min"],
            temp_max_f=main["temp_max"],
            humidity_pct=main["humidity"],
            pressure_hpa=main["pressure"],
            visibility_m=data.get("visibility", 0),
            wind_speed_mph=wind.get("speed", 0.0),
            wind_deg=wind.get("deg", 0),
            wind_gust_mph=wind.get("gust"),
            clouds_pct=data.get("clouds", {}).get("all", 0),
            condition=WeatherCondition(
                id=weather["id"],
                main=weather["main"],
                description=weather["description"],
                icon=weather["icon"],
            ),
            sunrise=datetime.fromtimestamp(sys.get("sunrise", 0), tz=UTC),
            sunset=datetime.fromtimestamp(sys.get("sunset", 0), tz=UTC),
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "lat": self.lat,
            "lon": self.lon,
            "fetched_at": self.fetched_at.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "temp_f": self.temp_f,
            "feels_like_f": self.feels_like_f,
            "temp_min_f": self.temp_min_f,
            "temp_max_f": self.temp_max_f,
            "humidity_pct": self.humidity_pct,
            "pressure_hpa": self.pressure_hpa,
            "visibility_m": self.visibility_m,
            "wind_speed_mph": self.wind_speed_mph,
            "wind_deg": self.wind_deg,
            "wind_gust_mph": self.wind_gust_mph,
            "clouds_pct": self.clouds_pct,
            "condition_id": self.condition.id,
            "condition_main": self.condition.main,
            "condition_description": self.condition.description,
            "condition_icon": self.condition.icon,
            "sunrise": self.sunrise.isoformat(),
            "sunset": self.sunset.isoformat(),
        }
