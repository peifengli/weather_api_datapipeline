from unittest.mock import MagicMock, patch

import pytest

from src.weather.cities import TRISTATE_CITIES, City
from src.weather.client import WeatherClient
from tests.unit.test_models import SAMPLE_API_RESPONSE

STAMFORD_CT = City("Stamford", "CT", 41.0534, -73.5387)


@pytest.mark.unit
class TestWeatherClient:
    def _mock_client(self) -> WeatherClient:
        return WeatherClient(api_key="test-key", units="imperial")

    def test_fetch_current_success(self):
        client = self._mock_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_API_RESPONSE
        mock_resp.raise_for_status.return_value = None

        with patch.object(client._session, "get", return_value=mock_resp):
            reading = client.fetch_current(STAMFORD_CT)

        assert reading is not None
        assert reading.city == "Stamford"
        assert reading.state == "CT"

    def test_fetch_current_http_error_returns_none(self):
        import requests
        client = self._mock_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")

        with patch.object(client._session, "get", return_value=mock_resp):
            reading = client.fetch_current(STAMFORD_CT)

        assert reading is None

    def test_fetch_current_request_exception_returns_none(self):
        import requests
        client = self._mock_client()

        with patch.object(client._session, "get", side_effect=requests.ConnectionError("timeout")):
            reading = client.fetch_current(STAMFORD_CT)

        assert reading is None

    def test_fetch_all_tristate_skips_failures(self):
        import requests
        client = self._mock_client()
        cities = [TRISTATE_CITIES[0], TRISTATE_CITIES[1]]

        mock_ok = MagicMock()
        mock_ok.json.return_value = SAMPLE_API_RESPONSE
        mock_ok.raise_for_status.return_value = None

        mock_fail = MagicMock()
        mock_fail.raise_for_status.side_effect = requests.HTTPError("503")

        with patch.object(client._session, "get", side_effect=[mock_ok, mock_fail]):
            results = client.fetch_all_tristate(cities, request_delay=0)

        assert len(results) == 1

    def test_fetch_all_tristate_request_params_include_lat_lon(self):
        client = self._mock_client()
        city = TRISTATE_CITIES[0]

        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_API_RESPONSE
        mock_resp.raise_for_status.return_value = None

        with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
            client.fetch_all_tristate([city], request_delay=0)

        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1]
        assert params["lat"] == city.lat
        assert params["lon"] == city.lon
        assert params["appid"] == "test-key"
