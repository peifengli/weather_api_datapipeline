"""
AWS Glue ETL Job: fetch_weather

Fetches current weather for all tri-state cities in parallel using Spark RDDs,
writes raw JSON to S3 partitioned by year/month/day/hour.

Execution chain:
  EventBridge Scheduler → Lambda → Glue Workflow → this job
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import boto3
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

# ── Job bootstrap ─────────────────────────────────────────────────────────────

args = getResolvedOptions(sys.argv, ["JOB_NAME", "S3_RAW_BUCKET", "SECRET_NAME"])

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

logger = glue_context.get_logger()

# ── City registry (inlined — no external import needed on workers) ─────────────

TRISTATE_CITIES = [
    ("New York City", "NY", 40.7128, -74.0060),
    ("Buffalo",       "NY", 42.8864, -78.8784),
    ("Rochester",     "NY", 43.1566, -77.6088),
    ("Albany",        "NY", 42.6526, -73.7562),
    ("Yonkers",       "NY", 40.9312, -73.8988),
    ("Syracuse",      "NY", 43.0481, -76.1474),
    ("White Plains",  "NY", 41.0340, -73.7629),
    ("Newark",        "NJ", 40.7357, -74.1724),
    ("Jersey City",   "NJ", 40.7178, -74.0431),
    ("Paterson",      "NJ", 40.9168, -74.1718),
    ("Elizabeth",     "NJ", 40.6640, -74.2107),
    ("Trenton",       "NJ", 40.2170, -74.7429),
    ("Edison",        "NJ", 40.5187, -74.4121),
    ("Bridgeport",    "CT", 41.1865, -73.1952),
    ("New Haven",     "CT", 41.3083, -72.9279),
    ("Stamford",      "CT", 41.0534, -73.5387),
    ("Hartford",      "CT", 41.7658, -72.6851),
    ("Waterbury",     "CT", 41.5582, -73.0515),
    ("Norwalk",       "CT", 41.1177, -73.4082),
]

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


# ── Worker-side fetch (runs on Spark executors) ────────────────────────────────

def _fetch_city(city: tuple, api_key: str) -> dict | None:
    """Executed on each Spark worker. Returns a flat record dict or None on failure."""
    import requests  # noqa: PLC0415

    name, state, lat, lon = city
    try:
        resp = requests.get(
            BASE_URL,
            params={"lat": lat, "lon": lon, "appid": api_key, "units": "imperial"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        main = data["main"]
        wind = data.get("wind", {})
        weather = data["weather"][0]
        sys_data = data.get("sys", {})
        now = datetime.now(timezone.utc).isoformat()

        return {
            "city": name,
            "state": state,
            "country": "US",
            "lat": lat,
            "lon": lon,
            "fetched_at": now,
            "observed_at": datetime.fromtimestamp(data["dt"], tz=timezone.utc).isoformat(),
            "temp_f": float(main["temp"]),
            "feels_like_f": float(main["feels_like"]),
            "temp_min_f": float(main["temp_min"]),
            "temp_max_f": float(main["temp_max"]),
            "humidity_pct": int(main["humidity"]),
            "pressure_hpa": int(main["pressure"]),
            "wind_speed_mph": float(wind.get("speed", 0.0)),
            "wind_deg": int(wind.get("deg", 0)),
            "clouds_pct": int(data.get("clouds", {}).get("all", 0)),
            "visibility_m": int(data.get("visibility", 0)),
            "condition_id": int(weather["id"]),
            "condition_main": weather["main"],
            "condition_description": weather["description"],
            "condition_icon": weather["icon"],
            "sunrise": datetime.fromtimestamp(
                sys_data.get("sunrise", 0), tz=timezone.utc
            ).isoformat(),
            "sunset": datetime.fromtimestamp(
                sys_data.get("sunset", 0), tz=timezone.utc
            ).isoformat(),
        }
    except Exception:
        # Log on driver after collect; returning None lets the pipeline continue
        return None


# ── Driver logic ───────────────────────────────────────────────────────────────

def _get_api_key(secret_name: str) -> str:
    import os

    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    client = boto3.client("secretsmanager", region_name=region)
    secret = json.loads(client.get_secret_value(SecretId=secret_name)["SecretString"])
    return secret["OPENWEATHERMAP_API_KEY"]


def main() -> None:
    raw_bucket = args["S3_RAW_BUCKET"]
    secret_name = args["SECRET_NAME"]

    logger.info(f"fetch_weather starting | bucket={raw_bucket}")

    # Retrieve API key on the driver only — broadcast to workers so each
    # executor reuses the same value without hitting Secrets Manager.
    api_key = _get_api_key(secret_name)
    api_key_bc = sc.broadcast(api_key)

    # Parallelize across cities — one Spark partition per city so all 19 HTTP
    # calls execute concurrently on the cluster instead of sequentially.
    cities_rdd = sc.parallelize(TRISTATE_CITIES, numSlices=len(TRISTATE_CITIES))
    results_rdd = cities_rdd.map(lambda city: _fetch_city(city, api_key_bc.value))
    valid_rdd = results_rdd.filter(lambda r: r is not None)

    records = valid_rdd.collect()
    failed = len(TRISTATE_CITIES) - len(records)

    if not records:
        logger.error("All city fetches failed — aborting job")
        raise RuntimeError("No weather data fetched")

    if failed > 0:
        logger.warn(f"{failed} cities failed to fetch and were skipped")

    logger.info(f"Fetched {len(records)}/{len(TRISTATE_CITIES)} cities")

    # Build DataFrame and add Hive partition columns so Spark writes into
    # the correct prefix: weather/year=.../month=.../day=.../hour=.../
    run_time = datetime.now(timezone.utc)
    df = spark.createDataFrame(records)
    df = (
        df.withColumn("year",  F.lit(run_time.year))
          .withColumn("month", F.lit(run_time.month))
          .withColumn("day",   F.lit(run_time.day))
          .withColumn("hour",  F.lit(run_time.hour))
    )

    output_path = f"s3://{raw_bucket}/weather"
    (
        df.write
          .mode("append")
          .partitionBy("year", "month", "day", "hour")
          .json(output_path)
    )

    logger.info(f"Job complete | records={len(records)} path={output_path}")
    job.commit()


main()
