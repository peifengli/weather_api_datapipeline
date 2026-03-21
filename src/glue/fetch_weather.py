"""
AWS Glue Python Shell Job: fetch_weather
Fetches current weather for all tri-state cities and stores raw JSON to S3.
Scheduled to run hourly via Airflow.
"""
from __future__ import annotations
import json
import logging
import sys
from datetime import datetime, timezone

import boto3

# Glue jobs receive --JOB_NAME and custom args via getResolvedOptions
try:
    from awsglue.utils import getResolvedOptions  # type: ignore[import]
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "S3_RAW_BUCKET", "SECRET_NAME", "ENVIRONMENT"])
except Exception:
    # Fallback for local testing
    import os
    args = {
        "JOB_NAME": "fetch_weather_local",
        "S3_RAW_BUCKET": os.getenv("S3_RAW_BUCKET", "weatherdata-raw"),
        "SECRET_NAME": os.getenv("SECRET_NAME", "weather-api-key"),
        "ENVIRONMENT": os.getenv("ENVIRONMENT", "local"),
    }

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("fetch_weather")

# Add src to path so we can import project modules when running in Glue
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config
from src.weather.client import WeatherClient
from src.weather.cities import TRISTATE_CITIES
from src.storage.s3 import upload_batch


def get_api_key(secret_name: str, region: str, endpoint_url: str | None) -> str:
    client = boto3.client("secretsmanager", region_name=region, endpoint_url=endpoint_url)
    response = client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return secret["OPENWEATHERMAP_API_KEY"]


def main() -> None:
    config = Config()
    s3_raw_bucket = args["S3_RAW_BUCKET"]
    secret_name = args["SECRET_NAME"]

    logger.info("Starting fetch_weather job | env=%s bucket=%s", config.environment, s3_raw_bucket)

    api_key = get_api_key(secret_name, config.aws_region, config.aws_endpoint_url)
    client = WeatherClient(api_key=api_key, units=config.weather_units)

    readings = client.fetch_all_tristate(TRISTATE_CITIES)

    if not readings:
        logger.error("No weather data fetched — aborting")
        sys.exit(1)

    run_time = datetime.now(timezone.utc)
    reading_dicts = [r.to_dict() for r in readings]

    keys = upload_batch(
        bucket=s3_raw_bucket,
        readings=reading_dicts,
        observed_at=run_time,
        endpoint_url=config.aws_endpoint_url,
        region=config.aws_region,
    )

    logger.info("Job complete | readings_fetched=%d files_uploaded=%d", len(readings), len(keys))


if __name__ == "__main__":
    main()
