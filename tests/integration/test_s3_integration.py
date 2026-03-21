import json
import pytest
from datetime import datetime, timezone
from moto import mock_aws

from src.storage.s3 import upload_raw, upload_batch, key_exists, raw_s3_key


OBS_TIME = datetime(2024, 3, 21, 15, 0, 0, tzinfo=timezone.utc)
RAW_BUCKET = "weatherdata-raw-test"
PROCESSED_BUCKET = "weatherdata-processed-test"


@pytest.mark.integration
class TestS3RoundTrip:
    def test_upload_then_exists(self, aws_s3):
        upload_raw(RAW_BUCKET, "buffalo_ny", {"city": "Buffalo", "temp_f": 45.0}, OBS_TIME)
        key = raw_s3_key("buffalo_ny", OBS_TIME)
        assert key_exists(RAW_BUCKET, key)

    def test_upload_then_read_back(self, aws_s3):
        payload = {"city": "Hartford", "state": "CT", "temp_f": 62.5, "humidity_pct": 70}
        upload_raw(RAW_BUCKET, "hartford_ct", payload, OBS_TIME)

        key = raw_s3_key("hartford_ct", OBS_TIME)
        obj = aws_s3.get_object(Bucket=RAW_BUCKET, Key=key)
        data = json.loads(obj["Body"].read())

        assert data["city"] == "Hartford"
        assert data["temp_f"] == 62.5
        assert data["humidity_pct"] == 70

    def test_upload_batch_all_present(self, aws_s3):
        readings = [
            {"city": "New York City", "state": "NY", "temp_f": 70.0},
            {"city": "Newark", "state": "NJ", "temp_f": 68.0},
            {"city": "Stamford", "state": "CT", "temp_f": 65.0},
        ]
        keys = upload_batch(RAW_BUCKET, readings, OBS_TIME)
        assert len(keys) == 3
        for key in keys:
            assert key_exists(RAW_BUCKET, key)

    def test_key_not_exists_for_missing_object(self, aws_s3):
        assert not key_exists(RAW_BUCKET, "weather/year=2024/nonexistent.json")
