"""
AWS Glue ETL Job: process_weather

Reads raw JSON for a given hour partition from S3, validates records with
Spark DataFrame operations, enriches with derived columns, and writes
compressed Parquet to the processed bucket — partitioned for fast Athena queries.

Writes are also registered in the Glue Data Catalog via DynamicFrame so
Athena can query without a separate crawler run.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from functools import reduce

from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

# ── Job bootstrap ─────────────────────────────────────────────────────────────

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "S3_RAW_BUCKET", "S3_PROCESSED_BUCKET", "ENVIRONMENT", "RUN_HOUR"],
)

sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)
job.init(args["JOB_NAME"], args)

logger = glue_context.get_logger()

# ── Constants ─────────────────────────────────────────────────────────────────

REQUIRED_COLS = [
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
    "condition_main",
    "condition_description",
]

CATALOG_DATABASE = f"weatherdata_{args['ENVIRONMENT']}"
CATALOG_TABLE = "weather_processed"


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_run_hour(run_hour: str) -> datetime:
    return datetime.strptime(run_hour, "%Y-%m-%dT%H").replace(tzinfo=timezone.utc)


def _raw_s3_path(bucket: str, dt: datetime) -> str:
    return (
        f"s3://{bucket}/weather/"
        f"year={dt.year}/month={dt.month}/"
        f"day={dt.day}/hour={dt.hour}/"
    )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    raw_bucket = args["S3_RAW_BUCKET"]
    processed_bucket = args["S3_PROCESSED_BUCKET"]
    run_hour = args["RUN_HOUR"]

    dt = _parse_run_hour(run_hour)
    input_path = _raw_s3_path(raw_bucket, dt)

    logger.info(f"process_weather starting | run_hour={run_hour} input={input_path}")

    # ── Ingest ────────────────────────────────────────────────────────────────
    # spark.read.json auto-infers schema and reads all part files in the prefix
    raw_df = (
        spark.read.option("recursiveFileLookup", "true")
        .option("multiLine", "false")
        .json(input_path)
    )
    raw_df.cache()
    total_count = raw_df.count()

    if total_count == 0:
        logger.error(f"No raw records found at {input_path} — aborting")
        raise RuntimeError("No raw data to process")

    logger.info(f"Loaded {total_count} raw records from {input_path}")

    # ── Validation (distributed, no Python loops) ─────────────────────────────
    not_null = reduce(
        lambda a, b: a & b,
        [F.col(c).isNotNull() for c in REQUIRED_COLS],
    )
    in_range = (
        F.col("temp_f").between(-100, 150)
        & F.col("humidity_pct").between(0, 100)
        & F.col("pressure_hpa").between(870, 1085)
        & (F.col("wind_speed_mph") >= 0)
    )

    valid_df = raw_df.filter(not_null & in_range)
    valid_df.cache()

    valid_count = valid_df.count()
    invalid_count = total_count - valid_count

    if invalid_count > 0:
        logger.warn(f"Dropped {invalid_count} records that failed validation")

    # ── Enrichment ────────────────────────────────────────────────────────────
    processed_df = (
        valid_df
        # Normalised slug for downstream joins / partitioning
        .withColumn(
            "city_slug",
            F.concat_ws(
                "_",
                F.lower(F.regexp_replace(F.col("city"), r"\s+", "_")),
                F.lower(F.col("state")),
            ),
        )
        # Audit column
        .withColumn("processed_at", F.lit(datetime.now(timezone.utc).isoformat()))
        # Hive partition columns — written as directory names by Spark
        .withColumn("year", F.lit(dt.year))
        .withColumn("month", F.lit(dt.month))
        .withColumn("day", F.lit(dt.day))
        .withColumn("hour", F.lit(dt.hour))
        # SI unit conversions for international consumers
        .withColumn("temp_c", F.round((F.col("temp_f") - 32) * 5 / 9, 2))
        .withColumn("feels_like_c", F.round((F.col("feels_like_f") - 32) * 5 / 9, 2))
        .withColumn("wind_speed_ms", F.round(F.col("wind_speed_mph") * 0.44704, 3))
    )

    # ── Write Parquet ─────────────────────────────────────────────────────────
    # Parquet + Snappy: ~10x smaller than JSON, vectorised reads in Athena,
    # partition pruning eliminates unneeded files from every query.
    output_path = f"s3://{processed_bucket}/weather"
    (
        processed_df.write.mode("append")
        .option("compression", "snappy")
        .partitionBy("year", "month", "day", "hour")
        .parquet(output_path)
    )

    logger.info(f"Parquet written | path={output_path}")

    # ── Update Glue Data Catalog ──────────────────────────────────────────────
    # DynamicFrame → catalog write keeps Athena table schema in sync without
    # waiting for the next crawler run.
    dynamic_frame = DynamicFrame.fromDF(processed_df, glue_context, "processed")
    glue_context.write_dynamic_frame.from_catalog(
        frame=dynamic_frame,
        database=CATALOG_DATABASE,
        table_name=CATALOG_TABLE,
        additional_options={
            "partitionKeys": ["year", "month", "day", "hour"],
            "enableUpdateCatalog": True,
        },
    )

    logger.info(
        f"Job complete | processed={valid_count} skipped={invalid_count} "
        f"catalog={CATALOG_DATABASE}.{CATALOG_TABLE}"
    )
    job.commit()


main()
