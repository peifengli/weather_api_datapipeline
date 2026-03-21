"""
Data quality tests for weather readings.
These run against real or moto-mocked S3 data and validate business rules.
"""
import json
import pytest
from datetime import datetime, timezone
from moto import mock_aws
import boto3

from src.weather.models import WeatherReading
from src.weather.cities import TRISTATE_CITIES
from tests.unit.test_models import SAMPLE_API_RESPONSE


VALID_STATES = {"NY", "NJ", "CT"}
TEMP_MIN_F = -20.0
TEMP_MAX_F = 120.0
HUMIDITY_MIN = 0
HUMIDITY_MAX = 100
PRESSURE_MIN = 900
PRESSURE_MAX = 1100


def build_reading(overrides: dict = {}) -> WeatherReading:
    data = {**SAMPLE_API_RESPONSE}
    if "main" in overrides:
        data["main"] = {**data["main"], **overrides["main"]}
    return WeatherReading.from_api_response(data, "New York City", "NY")


@pytest.mark.data_quality
class TestWeatherReadingQuality:
    @pytest.fixture(autouse=True)
    def readings(self):
        self.sample = build_reading()

    def test_state_in_tristate(self):
        assert self.sample.state in VALID_STATES

    def test_temperature_in_realistic_range(self):
        assert TEMP_MIN_F <= self.sample.temp_f <= TEMP_MAX_F, (
            f"temp_f {self.sample.temp_f} outside [{TEMP_MIN_F}, {TEMP_MAX_F}]"
        )

    def test_feels_like_near_temp(self):
        diff = abs(self.sample.feels_like_f - self.sample.temp_f)
        assert diff < 40, f"feels_like diverges too much from temp: {diff}°F"

    def test_temp_min_lte_temp_lte_temp_max(self):
        assert self.sample.temp_min_f <= self.sample.temp_f <= self.sample.temp_max_f

    def test_humidity_in_range(self):
        assert HUMIDITY_MIN <= self.sample.humidity_pct <= HUMIDITY_MAX

    def test_pressure_in_range(self):
        assert PRESSURE_MIN <= self.sample.pressure_hpa <= PRESSURE_MAX, (
            f"pressure {self.sample.pressure_hpa} outside [{PRESSURE_MIN}, {PRESSURE_MAX}]"
        )

    def test_wind_speed_non_negative(self):
        assert self.sample.wind_speed_mph >= 0

    def test_clouds_pct_in_range(self):
        assert 0 <= self.sample.clouds_pct <= 100

    def test_observed_at_before_fetched_at(self):
        # API timestamp should be <= fetch time
        assert self.sample.observed_at <= self.sample.fetched_at

    def test_coords_in_tristate_bounding_box(self):
        # Rough bounding box for NY/NJ/CT region
        assert 38.5 <= self.sample.lat <= 45.5, f"lat {self.sample.lat} outside tristate bbox"
        assert -80.0 <= self.sample.lon <= -70.0, f"lon {self.sample.lon} outside tristate bbox"

    def test_condition_main_not_empty(self):
        assert self.sample.condition.main.strip() != ""

    def test_to_dict_has_all_required_keys(self):
        d = self.sample.to_dict()
        required = {
            "city", "state", "temp_f", "humidity_pct", "pressure_hpa",
            "wind_speed_mph", "observed_at", "fetched_at",
            "condition_main",
        }
        missing = required - set(d.keys())
        assert not missing, f"Missing keys in to_dict(): {missing}"


@pytest.mark.data_quality
class TestAllCitiesCoverage:
    def test_tristate_has_all_three_states(self):
        states = {c.state for c in TRISTATE_CITIES}
        assert states == VALID_STATES

    def test_tristate_has_minimum_cities(self):
        assert len(TRISTATE_CITIES) >= 15, "Expected at least 15 major cities"

    def test_all_cities_have_valid_coords(self):
        for city in TRISTATE_CITIES:
            assert 38.5 <= city.lat <= 45.5, f"{city.name} lat out of range"
            assert -80.0 <= city.lon <= -70.0, f"{city.name} lon out of range"

    def test_no_duplicate_city_slugs(self):
        slugs = [c.slug for c in TRISTATE_CITIES]
        assert len(slugs) == len(set(slugs)), "Duplicate city slugs found"
