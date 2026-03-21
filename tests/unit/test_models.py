import pytest
from datetime import datetime, timezone
from src.weather.models import WeatherReading, WeatherCondition


SAMPLE_API_RESPONSE = {
    "coord": {"lon": -74.006, "lat": 40.7128},
    "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
    "main": {
        "temp": 72.5,
        "feels_like": 70.1,
        "temp_min": 68.0,
        "temp_max": 75.0,
        "pressure": 1013,
        "humidity": 65,
    },
    "visibility": 10000,
    "wind": {"speed": 5.2, "deg": 180, "gust": 8.1},
    "clouds": {"all": 0},
    "dt": 1711900000,
    "sys": {"country": "US", "sunrise": 1711877000, "sunset": 1711922000},
    "timezone": -14400,
    "id": 5128581,
    "name": "New York",
    "cod": 200,
}


@pytest.mark.unit
class TestWeatherReading:
    def test_from_api_response_fields(self):
        reading = WeatherReading.from_api_response(SAMPLE_API_RESPONSE, "New York City", "NY")

        assert reading.city == "New York City"
        assert reading.state == "NY"
        assert reading.country == "US"
        assert reading.lat == 40.7128
        assert reading.lon == -74.006
        assert reading.temp_f == 72.5
        assert reading.feels_like_f == 70.1
        assert reading.temp_min_f == 68.0
        assert reading.temp_max_f == 75.0
        assert reading.humidity_pct == 65
        assert reading.pressure_hpa == 1013
        assert reading.visibility_m == 10000
        assert reading.wind_speed_mph == 5.2
        assert reading.wind_deg == 180
        assert reading.wind_gust_mph == 8.1
        assert reading.clouds_pct == 0

    def test_condition_parsed(self):
        reading = WeatherReading.from_api_response(SAMPLE_API_RESPONSE, "New York City", "NY")
        assert reading.condition.main == "Clear"
        assert reading.condition.description == "clear sky"
        assert reading.condition.icon == "01d"

    def test_missing_gust_defaults_to_none(self):
        data = {**SAMPLE_API_RESPONSE, "wind": {"speed": 3.0, "deg": 90}}
        reading = WeatherReading.from_api_response(data, "Albany", "NY")
        assert reading.wind_gust_mph is None

    def test_to_dict_roundtrip(self):
        reading = WeatherReading.from_api_response(SAMPLE_API_RESPONSE, "New York City", "NY")
        d = reading.to_dict()
        assert d["city"] == "New York City"
        assert d["state"] == "NY"
        assert d["temp_f"] == 72.5
        assert "observed_at" in d
        assert "fetched_at" in d

    def test_fetched_at_defaults_to_now(self):
        before = datetime.now(timezone.utc)
        reading = WeatherReading.from_api_response(SAMPLE_API_RESPONSE, "Newark", "NJ")
        after = datetime.now(timezone.utc)
        assert before <= reading.fetched_at <= after
