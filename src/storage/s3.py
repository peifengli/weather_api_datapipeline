from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def _s3_client(endpoint_url: str | None = None, region: str = "us-east-1"):
    return boto3.client("s3", region_name=region, endpoint_url=endpoint_url)


def raw_s3_key(city_slug: str, observed_at: datetime) -> str:
    """Partition path: weather/year=YYYY/month=MM/day=DD/hour=HH/<city_slug>.json"""
    return (
        f"weather/"
        f"year={observed_at.year:04d}/"
        f"month={observed_at.month:02d}/"
        f"day={observed_at.day:02d}/"
        f"hour={observed_at.hour:02d}/"
        f"{city_slug}.json"
    )


def upload_raw(
    bucket: str,
    city_slug: str,
    payload: dict[str, Any],
    observed_at: datetime,
    endpoint_url: str | None = None,
    region: str = "us-east-1",
) -> str:
    key = raw_s3_key(city_slug, observed_at)
    client = _s3_client(endpoint_url, region)
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, default=str).encode("utf-8"),
        ContentType="application/json",
    )
    logger.debug("Uploaded s3://%s/%s", bucket, key)
    return key


def upload_batch(
    bucket: str,
    readings: list[dict[str, Any]],
    observed_at: datetime,
    endpoint_url: str | None = None,
    region: str = "us-east-1",
) -> list[str]:
    uploaded: list[str] = []
    for reading in readings:
        city_slug = f"{reading['city'].lower().replace(' ', '_')}_{reading['state'].lower()}"
        key = upload_raw(bucket, city_slug, reading, observed_at, endpoint_url, region)
        uploaded.append(key)
    return uploaded


def key_exists(
    bucket: str, key: str, endpoint_url: str | None = None, region: str = "us-east-1"
) -> bool:
    client = _s3_client(endpoint_url, region)
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise
