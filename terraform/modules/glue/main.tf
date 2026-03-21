resource "aws_glue_catalog_database" "weather" {
  name = "${var.project}_${var.environment}"
}

# ── Shared Spark defaults injected into both jobs ─────────────────────────────

locals {
  spark_defaults = {
    "--enable-metrics"                   = ""
    "--enable-continuous-cloudwatch-log" = "true"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--conf"                             = "spark.sql.parquet.compression.codec=snappy"
  }
}

# ── fetch_weather ─────────────────────────────────────────────────────────────

resource "aws_glue_job" "fetch_weather" {
  name         = "fetch_weather_${var.environment}"
  role_arn     = var.glue_role_arn
  glue_version = "4.0"

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.scripts_bucket}/glue-scripts/fetch_weather.py"
  }

  # G.1X = 4 vCPU / 16 GB per worker; 2 workers = 1 driver + 1 executor
  worker_type       = "G.1X"
  number_of_workers = 2

  default_arguments = merge(local.spark_defaults, {
    "--S3_RAW_BUCKET" = var.s3_raw_bucket
    "--SECRET_NAME"   = var.secret_name
    "--ENVIRONMENT"   = var.environment
  })

  tags = var.tags
}

# ── process_weather ───────────────────────────────────────────────────────────

resource "aws_glue_job" "process_weather" {
  name         = "process_weather_${var.environment}"
  role_arn     = var.glue_role_arn
  glue_version = "4.0"

  command {
    name            = "glueetl"
    python_version  = "3"
    script_location = "s3://${var.scripts_bucket}/glue-scripts/process_weather.py"
  }

  worker_type       = "G.1X"
  number_of_workers = 2

  default_arguments = merge(local.spark_defaults, {
    "--S3_RAW_BUCKET"       = var.s3_raw_bucket
    "--S3_PROCESSED_BUCKET" = var.s3_processed_bucket
    "--ENVIRONMENT"         = var.environment
    # RUN_HOUR is passed at runtime by the Glue Workflow trigger
  })

  tags = var.tags
}

# ── Crawler (keeps Athena table in sync for ad-hoc queries) ──────────────────
# Note: process_weather now also writes directly to the catalog via
# write_dynamic_frame, so the crawler is a fallback safety net.

resource "aws_glue_crawler" "weather" {
  name          = "${var.project}-crawler-${var.environment}"
  role          = var.glue_role_arn
  database_name = aws_glue_catalog_database.weather.name

  s3_target {
    path = "s3://${var.s3_processed_bucket}/weather/"
  }

  # Run 5 minutes after the top of every hour as a reconciliation pass
  schedule = "cron(5 * * * ? *)"

  tags = var.tags
}
