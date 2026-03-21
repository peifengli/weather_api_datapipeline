# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Weather API data pipeline that fetches data from OpenWeatherMap and processes it through AWS services (S3, Glue, Athena) with Apache Airflow orchestration and Apache Superset for visualization. Local development uses LocalStack to emulate AWS services.

## Commands

### Local Development

```bash
make up              # Start full local stack (Airflow + LocalStack + Superset)
make down            # Stop all services
make init-localstack # Bootstrap AWS resources in LocalStack
```

Local service URLs:
- Airflow UI: http://localhost:8080 (admin/admin)
- Superset: http://localhost:8088 (admin/admin)
- LocalStack: http://localhost:4566
- Flower (Celery monitor): http://localhost:5555

### Testing

```bash
make test            # All tests (unit + integration + data quality)
make test-unit       # Unit tests only (no external deps)
make test-integration # Integration tests (requires LocalStack running)
make test-quality    # Great Expectations data quality tests
make test-dbt        # DBT schema + data quality tests
make test-all        # Complete test suite

# Run a single test file
pytest tests/unit/test_foo.py -v
# Run tests by marker
pytest -m unit -v
pytest -m integration -v
```

### Code Quality

```bash
make lint        # Ruff linting
make format      # Black + Ruff formatting
make type-check  # MyPy type checking
make pre-commit  # Run all pre-commit hooks
```

### DBT

```bash
make dbt-run   # Execute DBT transformations
make dbt-test  # Run DBT data quality tests
make dbt-docs  # Generate and serve DBT documentation
```

## Architecture

Data flows through these layers:

1. **Ingestion**: Airflow DAGs trigger AWS Glue jobs to fetch from OpenWeatherMap API; API keys stored in AWS Secrets Manager
2. **Raw Storage**: JSON responses land in S3 (`weatherdata-raw-*` bucket)
3. **Processing**: AWS Glue jobs transform raw JSON; DBT models run additional transformations
4. **Processed Storage**: Transformed data in S3 (`weatherdata-processed-*` bucket)
5. **Catalog**: AWS Glue Data Catalog maintains metadata; Athena enables SQL queries
6. **Visualization**: Apache Superset connects to Athena for dashboards

**Local stack** (docker-compose): PostgreSQL (Airflow metadata) + Redis (Celery broker) + Airflow (webserver/scheduler/worker) + Flower + LocalStack + Superset

## Key Configuration

Copy `.env.example` to `.env` before running locally. Required values:
- `OPENWEATHERMAP_API_KEY` + location (lat/lon/city)
- AWS credentials and S3 bucket names
- Athena database and workgroup settings

## Project Layout (planned)

```
src/              # Application source code
airflow/dags/     # Airflow DAG definitions
airflow/plugins/  # Custom operators/hooks
dbt/              # DBT transformation models
terraform/        # AWS infrastructure (Glue, S3, Athena, Secrets Manager)
tests/
  unit/           # Fast tests, no external deps
  integration/    # Tests against LocalStack
  data_quality/   # Great Expectations suites
```

## Test Markers

Defined in `pyproject.toml`: `unit`, `integration`, `data_quality`, `slow`. Use `-m <marker>` to filter.

## Python Version

3.11 (enforced via pyproject.toml). Line length: 100.
