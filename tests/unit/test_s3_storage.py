import json
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

from src.storage.s3 import raw_s3_key, upload_raw, upload_batch


OBS_TIME = datetime(2024, 3, 21, 15, 0, 0, tzinfo=timezone.utc)


@pytest.mark.unit
class TestS3Key:
    def test_raw_s3_key_format(self):
        key = raw_s3_key("new_york_city_ny", OBS_TIME)
        assert key == "weather/year=2024/month=03/day=21/hour=15/new_york_city_ny.json"

    def test_raw_s3_key_midnight(self):
        midnight = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        key = raw_s3_key("newark_nj", midnight)
        assert "hour=00" in key
        assert "month=01" in key
        assert "day=01" in key


@pytest.mark.unit
class TestUploadRaw:
    def test_upload_raw_calls_put_object(self):
        mock_client = MagicMock()
        with patch("src.storage.s3._s3_client", return_value=mock_client):
            key = upload_raw("my-bucket", "newark_nj", {"temp_f": 55.0}, OBS_TIME)

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "my-bucket"
        assert call_kwargs["ContentType"] == "application/json"
        payload = json.loads(call_kwargs["Body"])
        assert payload["temp_f"] == 55.0

    def test_upload_raw_returns_key(self):
        mock_client = MagicMock()
        with patch("src.storage.s3._s3_client", return_value=mock_client):
            key = upload_raw("bucket", "hartford_ct", {}, OBS_TIME)
        assert key == "weather/year=2024/month=03/day=21/hour=15/hartford_ct.json"


@pytest.mark.unit
class TestUploadBatch:
    def test_upload_batch_returns_one_key_per_reading(self):
        readings = [
            {"city": "New York City", "state": "NY", "temp_f": 70.0},
            {"city": "Newark", "state": "NJ", "temp_f": 68.0},
        ]
        mock_client = MagicMock()
        with patch("src.storage.s3._s3_client", return_value=mock_client):
            keys = upload_batch("bucket", readings, OBS_TIME)
        assert len(keys) == 2
        assert mock_client.put_object.call_count == 2
