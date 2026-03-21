"""
Hourly weather data pipeline DAG.

Schedule: every hour at :05
Task chain: fetch_weather → process_weather → dbt_run → dbt_test

Environment behaviour:
  ENVIRONMENT=local  → PythonOperator (runs src/ code directly, no Glue needed)
  ENVIRONMENT=dev/prod → GlueJobOperator (submits jobs to real AWS Glue)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
IS_LOCAL = ENVIRONMENT == "local"

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "email_on_failure": False,
}


# ── Local implementations (PythonOperator callables) ─────────────────────────

def _fetch_weather_local(**context) -> None:
    """Runs the fetch job in-process — no Glue needed for local dev."""
    import sys
    sys.path.insert(0, "/opt/airflow")

    from src.config import Config
    from src.weather.client import WeatherClient
    from src.weather.cities import TRISTATE_CITIES
    from src.storage.s3 import upload_batch
    import boto3
    import json
    from datetime import timezone

    config = Config()

    # Retrieve API key from LocalStack Secrets Manager
    sm = boto3.client(
        "secretsmanager",
        region_name=config.aws_region,
        endpoint_url=config.aws_endpoint_url,
    )
    secret = json.loads(sm.get_secret_value(SecretId="openweather_api_key")["SecretString"])
    api_key = secret.get("OPENWEATHERMAP_API_KEY") or secret.get("api_key", "")

    client = WeatherClient(api_key=api_key, units=config.weather_units)
    readings = client.fetch_all_tristate(TRISTATE_CITIES)

    if not readings:
        raise RuntimeError("No weather data fetched")

    run_time = datetime.now(timezone.utc)
    upload_batch(
        bucket=config.s3_raw_bucket,
        readings=[r.to_dict() for r in readings],
        observed_at=run_time,
        endpoint_url=config.aws_endpoint_url,
        region=config.aws_region,
    )


def _process_weather_local(**context) -> None:
    """Runs the process job in-process — no Glue needed for local dev."""
    import sys
    sys.path.insert(0, "/opt/airflow")

    execution_date = context["execution_date"]
    run_hour = execution_date.strftime("%Y-%m-%dT%H")

    import src.glue.process_weather as pw_module
    pw_module.args["RUN_HOUR"] = run_hour
    pw_module.main()


def _run_dbt(**context) -> None:
    import subprocess
    target = "local" if IS_LOCAL else "dev"
    result = subprocess.run(
        ["dbt", "run", "--profiles-dir", "/opt/airflow/dbt",
         "--target", target, "--project-dir", "/opt/airflow/dbt"],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"dbt run failed:\n{result.stderr}")


def _run_dbt_tests(**context) -> None:
    import subprocess
    target = "local" if IS_LOCAL else "dev"
    result = subprocess.run(
        ["dbt", "test", "--profiles-dir", "/opt/airflow/dbt",
         "--target", target, "--project-dir", "/opt/airflow/dbt"],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(f"dbt test failed:\n{result.stderr}")


# ── DAG definition ────────────────────────────────────────────────────────────

with DAG(
    dag_id="weather_pipeline",
    default_args=DEFAULT_ARGS,
    description="Tri-state weather data ingestion and processing (every 15 min)",
    schedule_interval="*/15 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["weather", "ingestion", "hourly"],
) as dag:

    if IS_LOCAL:
        # ── Local: run Python functions directly, no Glue ─────────────────────
        fetch_weather = PythonOperator(
            task_id="fetch_weather",
            python_callable=_fetch_weather_local,
        )

        process_weather = PythonOperator(
            task_id="process_weather",
            python_callable=_process_weather_local,
        )

    else:
        # ── Dev / Prod: submit to real AWS Glue ───────────────────────────────
        from airflow.providers.amazon.aws.operators.glue import GlueJobOperator

        fetch_weather = GlueJobOperator(
            task_id="fetch_weather",
            job_name=f"fetch_weather_{ENVIRONMENT}",
            script_args={
                "--S3_RAW_BUCKET": Variable.get("s3_raw_bucket", default_var="weatherdata-raw"),
                "--SECRET_NAME": Variable.get("weather_secret_name", default_var="weather-api-key"),
                "--ENVIRONMENT": ENVIRONMENT,
            },
            aws_conn_id="aws_default",
            wait_for_completion=True,
            verbose=True,
        )

        process_weather = GlueJobOperator(
            task_id="process_weather",
            job_name=f"process_weather_{ENVIRONMENT}",
            script_args={
                "--S3_RAW_BUCKET": Variable.get("s3_raw_bucket", default_var="weatherdata-raw"),
                "--S3_PROCESSED_BUCKET": Variable.get("s3_processed_bucket", default_var="weatherdata-processed"),
                "--ENVIRONMENT": ENVIRONMENT,
                "--RUN_HOUR": "{{ execution_date.strftime('%Y-%m-%dT%H') }}",
            },
            aws_conn_id="aws_default",
            wait_for_completion=True,
            verbose=True,
        )

    dbt_run = PythonOperator(
        task_id="dbt_run",
        python_callable=_run_dbt,
    )

    dbt_test = PythonOperator(
        task_id="dbt_test",
        python_callable=_run_dbt_tests,
    )

    fetch_weather >> process_weather >> dbt_run >> dbt_test
