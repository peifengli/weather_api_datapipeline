"""
AWS Glue Python Shell Job: process_weather
Reads raw JSON files from S3, flattens/validates, writes processed JSON back to S3.
Runs after fetch_weather completes.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

import boto3

try:
    from awsglue.utils import getResolvedOptions  # type: ignore[import]

    args = getResolvedOptions(
        sys.argv,
        ["JOB_NAME", "S3_RAW_BUCKET", "S3_PROCESSED_BUCKET", "ENVIRONMENT", "RUN_HOUR"],
    )
except Exception:
    import os

    now = datetime.now(UTC)
    args = {
        "JOB_NAME": "process_weather_local",
        "S3_RAW_BUCKET": os.getenv("S3_RAW_BUCKET", "weatherdata-raw"),
        "S3_PROCESSED_BUCKET": os.getenv("S3_PROCESSED_BUCKET", "weatherdata-processed"),
        "ENVIRONMENT": os.getenv("ENVIRONMENT", "local"),
        "RUN_HOUR": now.strftime("%Y-%m-%dT%H"),
    }

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("process_weather")

import os  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config  # noqa: E402

REQUIRED_FIELDS = {
    "city",
    "state",
    "country",
    "lat",
    "lon",
    "fetched_at",
    "observed_at",
    "temp_f",
    "feels_like_f",
    "temp_min_f",
    "temp_max_f",
    "humidity_pct",
    "pressure_hpa",
    "wind_speed_mph",
    "wind_deg",
    "clouds_pct",
    "condition_main",
    "condition_description",
}


def _list_raw_keys(s3_client, bucket: str, prefix: str) -> list[str]:
    paginator = s3_client.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys


def _build_raw_prefix(run_hour: str) -> str:
    dt = datetime.strptime(run_hour, "%Y-%m-%dT%H")
    return (
        f"weather/"
        f"year={dt.year:04d}/"
        f"month={dt.month:02d}/"
        f"day={dt.day:02d}/"
        f"hour={dt.hour:02d}/"
    )


def _processed_key(city_slug: str, run_hour: str) -> str:
    dt = datetime.strptime(run_hour, "%Y-%m-%dT%H")
    return (
        f"weather/"
        f"year={dt.year:04d}/month={dt.month:02d}/day={dt.day:02d}/"
        f"{city_slug}_{dt.hour:02d}00.json"
    )


def validate(record: dict) -> list[str]:
    missing = [f for f in REQUIRED_FIELDS if record.get(f) is None]
    errors = []
    if missing:
        errors.append(f"Missing fields: {missing}")
    if record.get("temp_f") is not None and not (-100 < record["temp_f"] < 150):
        errors.append(f"temp_f out of range: {record['temp_f']}")
    if record.get("humidity_pct") is not None and not (0 <= record["humidity_pct"] <= 100):
        errors.append(f"humidity_pct out of range: {record['humidity_pct']}")
    return errors


def main() -> None:
    config = Config()
    raw_bucket = args["S3_RAW_BUCKET"]
    processed_bucket = args["S3_PROCESSED_BUCKET"]
    run_hour = args["RUN_HOUR"]

    logger.info("Starting process_weather | run_hour=%s", run_hour)

    s3 = boto3.client("s3", region_name=config.aws_region, endpoint_url=config.aws_endpoint_url)

    prefix = _build_raw_prefix(run_hour)
    raw_keys = _list_raw_keys(s3, raw_bucket, prefix)
    logger.info("Found %d raw files under s3://%s/%s", len(raw_keys), raw_bucket, prefix)

    processed, skipped = 0, 0
    for key in raw_keys:
        obj = s3.get_object(Bucket=raw_bucket, Key=key)
        record = json.loads(obj["Body"].read())

        errors = validate(record)
        if errors:
            logger.warning("Validation failed for %s: %s", key, errors)
            skipped += 1
            continue

        city_slug = f"{record['city'].lower().replace(' ', '_')}_{record['state'].lower()}"
        out_key = _processed_key(city_slug, run_hour)

        s3.put_object(
            Bucket=processed_bucket,
            Key=out_key,
            Body=json.dumps(record, default=str).encode("utf-8"),
            ContentType="application/json",
        )
        processed += 1

    logger.info("Job complete | processed=%d skipped=%d", processed, skipped)
    if skipped > 0:
        logger.warning("%d records skipped due to validation errors", skipped)


if __name__ == "__main__":
    main()
