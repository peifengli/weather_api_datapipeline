#!/usr/bin/env python3
"""Sync processed weather data from LocalStack (or real) S3 into a DuckDB file
that Apache Superset can query persistently.

Creates three tables:
  weather_processed       – full processed dataset (all columns, all partitions)
  weather_current         – latest reading per city
  weather_hourly_summary  – hourly aggregates per city

Usage:
    python scripts/s3_to_duckdb.py
    python scripts/s3_to_duckdb.py --output data/weather.db
    python scripts/s3_to_duckdb.py --env dev
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = "data/weather.db"
DEFAULT_ENV = os.getenv("ENVIRONMENT", "local")
# When running on the host, docker-internal hostnames aren't reachable.
# Replace known internal aliases with localhost.
_DOCKER_INTERNAL_HOSTS = {"localstack", "airflow-webserver", "postgres"}


def _resolve_endpoint(raw: str) -> str:
    """Swap docker-internal hostnames for localhost when running on the host."""
    for host in _DOCKER_INTERNAL_HOSTS:
        if f"://{host}" in raw:
            return raw.replace(f"://{host}", "://localhost")
    return raw


def _s3_cfg(env: str, endpoint_override: str | None = None) -> dict:
    raw = endpoint_override or os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
    endpoint = _resolve_endpoint(raw)
    return {
        "bucket": os.getenv("S3_PROCESSED_BUCKET", f"weatherdata-processed-{env}"),
        # DuckDB wants the host:port without the scheme
        "endpoint": endpoint.removeprefix("https://").removeprefix("http://"),
        "access_key": os.getenv("AWS_ACCESS_KEY_ID", "test"),
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        "use_ssl": endpoint.startswith("https://"),
    }


def _configure_s3(conn, cfg: dict) -> None:
    use_ssl = "true" if cfg["use_ssl"] else "false"
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute(f"""
        SET s3_endpoint='{cfg["endpoint"]}';
        SET s3_access_key_id='{cfg["access_key"]}';
        SET s3_secret_access_key='{cfg["secret_key"]}';
        SET s3_region='{cfg["region"]}';
        SET s3_use_ssl={use_ssl};
        SET s3_url_style='path';
    """)


def sync(db_path: str, env: str, endpoint_override: str | None = None) -> None:
    try:
        import duckdb
    except ModuleNotFoundError:
        sys.exit("duckdb is not installed. Run: pip install duckdb")

    cfg = _s3_cfg(env, endpoint_override)
    file_glob = f"s3://{cfg['bucket']}/weather/**/*.json"

    print(f"Output : {Path(db_path).resolve()}")
    print(f"Source : {file_glob}")
    print(f"S3 host: {cfg['endpoint']}\n")

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(db_path)

    _configure_s3(conn, cfg)

    # ── Full processed table ──────────────────────────────────────────────────
    print("Building weather_processed …")
    conn.execute(f"""
        CREATE OR REPLACE TABLE weather_processed AS
        SELECT
            city,
            state,
            country,
            lat,
            lon,
            observed_at::TIMESTAMP   AS observed_at,
            fetched_at::TIMESTAMP    AS fetched_at,
            processed_at::TIMESTAMP  AS processed_at,
            temp_f,
            feels_like_f,
            temp_min_f,
            temp_max_f,
            temp_c,
            feels_like_c,
            humidity_pct,
            pressure_hpa,
            visibility_m,
            wind_speed_mph,
            wind_speed_ms,
            wind_deg,
            wind_gust_mph,
            clouds_pct,
            condition_id,
            condition_main,
            condition_description,
            condition_icon,
            city_slug,
            year, month, day, hour
        FROM read_json('{file_glob}', format = 'newline_delimited', hive_partitioning = true, auto_detect = true)
    """)
    n = conn.execute("SELECT COUNT(*) FROM weather_processed").fetchone()[0]
    print(f"  {n:,} rows")

    # ── Latest reading per city ───────────────────────────────────────────────
    print("Building weather_current …")
    conn.execute("""
        CREATE OR REPLACE TABLE weather_current AS
        SELECT DISTINCT ON (city_slug)
            city                AS city_name,
            state               AS state_code,
            country             AS country_code,
            lat                 AS latitude,
            lon                 AS longitude,
            observed_at,
            temp_f,
            feels_like_f,
            temp_min_f,
            temp_max_f,
            temp_c,
            feels_like_c,
            humidity_pct,
            pressure_hpa,
            visibility_m,
            wind_speed_mph,
            wind_gust_mph,
            clouds_pct,
            condition_main,
            condition_description,
            city_slug
        FROM weather_processed
        ORDER BY city_slug, observed_at DESC
    """)
    n = conn.execute("SELECT COUNT(*) FROM weather_current").fetchone()[0]
    print(f"  {n:,} rows")

    # ── Hourly aggregates per city ────────────────────────────────────────────
    print("Building weather_hourly_summary …")
    conn.execute("""
        CREATE OR REPLACE TABLE weather_hourly_summary AS
        SELECT
            city                                            AS city_name,
            state                                           AS state_code,
            date_trunc('hour', observed_at)                 AS observed_hour,
            ROUND(AVG(temp_f), 2)                           AS avg_temp_f,
            MIN(temp_f)                                     AS min_temp_f,
            MAX(temp_f)                                     AS max_temp_f,
            ROUND(AVG(feels_like_f), 2)                     AS avg_feels_like_f,
            ROUND(AVG(humidity_pct), 2)                     AS avg_humidity_pct,
            ROUND(AVG(pressure_hpa), 2)                     AS avg_pressure_hpa,
            ROUND(AVG(wind_speed_mph), 2)                   AS avg_wind_speed_mph,
            MAX(wind_gust_mph)                              AS max_wind_gust_mph,
            ROUND(AVG(clouds_pct), 2)                       AS avg_clouds_pct,
            mode() WITHIN GROUP (ORDER BY condition_main)   AS dominant_condition,
            COUNT(*)                                        AS reading_count
        FROM weather_processed
        GROUP BY city, state, date_trunc('hour', observed_at)
        ORDER BY city_name, observed_hour
    """)
    n = conn.execute("SELECT COUNT(*) FROM weather_hourly_summary").fetchone()[0]
    print(f"  {n:,} rows")

    conn.close()
    print("\nDone. Connect Superset to: duckdb:////app/data/weather.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync S3 weather data → DuckDB")
    parser.add_argument("--output", default=DEFAULT_DB_PATH, metavar="PATH",
                        help=f"DuckDB file path (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--env", default=DEFAULT_ENV, metavar="ENV",
                        help=f"Environment suffix for bucket name (default: {DEFAULT_ENV})")
    parser.add_argument("--endpoint", default=None, metavar="URL",
                        help="Override S3 endpoint URL (e.g. http://localhost:4566)")
    args = parser.parse_args()
    sync(db_path=args.output, env=args.env, endpoint_override=args.endpoint)


if __name__ == "__main__":
    main()
