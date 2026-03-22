# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Hourly weather data pipeline for 19 tri-state cities (NY/NJ/CT). Fetches from OpenWeatherMap every 30 minutes, processes through AWS Glue (PySpark), stores Parquet in S3, transforms with DBT, and serves via a Streamlit dashboard on ECS Fargate + ALB.

**Local dev** uses LocalStack (mock AWS) + Airflow. **Production** uses real AWS services deployed via Terraform + GitHub Actions CD.

## Architecture

```
EventBridge (30 min) → Lambda → Glue Workflow
  fetch_weather  → s3://weatherdata-raw-{env}/weather/year=X/month=X/day=X/hour=X/
  process_weather → s3://weatherdata-processed-{env}/weather/**/*.parquet (hive-partitioned)
    → DBT models → Athena
    → Streamlit dashboard (ECS Fargate + ALB, prod) reads S3 via DuckDB httpfs
```

Local: Airflow DAGs replicate the Glue logic using Python operators against LocalStack.

## Key Commands

### Local stack
```bash
make up                    # start Airflow + LocalStack + Streamlit (port 8501)
make down                  # stop all services
make down-scheduler        # stop Airflow scheduler/worker only
make refresh-db            # sync LocalStack S3 → data/weather.db (DuckDB)
make dashboard             # run Streamlit locally at localhost:8501
make init-localstack       # re-bootstrap S3 buckets + Secrets Manager
```

### Testing
```bash
make test                  # unit + integration + data quality
make test-unit             # fast, no external deps
make test-integration      # requires LocalStack running
make test-dbt              # DBT schema + data quality tests
```

### Code quality
```bash
make lint / format / type-check / pre-commit
```

### DBT
```bash
make dbt-run               # run models (local DuckDB target)
make dbt-run-prod          # run against production Athena
make dbt-test / dbt-docs
```

### Dev cloud cost saving
```bash
make disable-dev-scheduling   # disable EventBridge in AWS dev (stops Glue runs)
make enable-dev-scheduling    # re-enable
```

## Local Service URLs

| Service | URL | Creds |
|---|---|---|
| Airflow | http://localhost:8080 | admin/admin |
| Streamlit | http://localhost:8501 | — |
| Superset | http://localhost:8088 | admin/admin |
| LocalStack | http://localhost:4566 | — |

## Project Layout

```
app/dashboard.py            # Streamlit dashboard (local + prod)
airflow/dags/               # Airflow DAG (local dev only)
dbt/                        # DBT models
docker/streamlit/Dockerfile # python:3.11-slim + streamlit/plotly/duckdb/boto3/tzdata
scripts/s3_to_duckdb.py     # sync S3 processed data → local DuckDB
src/glue/                   # Glue job scripts (fetch + process)
src/lambda/                 # Lambda trigger script
terraform/modules/          # ecs, athena, glue, iam, s3, scheduler
terraform/environments/     # dev/ and prod/ configs
tests/unit|integration|data_quality/
.github/workflows/ci.yml    # lint + test on PR
.github/workflows/cd.yml    # deploy dev → prod on merge to main
```

## Dashboard Architecture (app/dashboard.py)

- **Local** (`ENVIRONMENT=local`): reads from `data/weather.db` (DuckDB file, populated by `make refresh-db`)
- **Prod** (`ENVIRONMENT=prod`): reads S3 directly via DuckDB httpfs using ECS task IAM role
- `_s3_conn()`: sets up in-memory DuckDB with httpfs + boto3 credential chain for prod
- `db_exists()`: returns `True` in prod (no file check needed)
- `load_current()`, `load_hourly()`, `load_processed()`: branch on `_ENV`

Parquet schema note: `observed_at` is stored as VARCHAR (ISO 8601). All prod queries cast it with `::TIMESTAMP`. `wind_gust_mph` does not exist in the OpenWeatherMap free tier — do not reference it.

Key constants: `CITY_POPULATIONS` (19 cities), `CITY_ACTIVITIES` (seasonal activity advisor), `_TEMP_ANCHORS` (colour scale).

## CI/CD Pipeline

`ci.yml` (on PR): lint → unit tests → integration tests → data quality → terraform validate

`cd.yml` (on merge to main):
1. CI gate
2. Deploy dev (auto): terraform apply + upload Glue scripts
3. Smoke tests against dev
4. Deploy prod (manual approval):
   - Destroy old App Runner resources if still in state (migration step, idempotent)
   - `terraform apply -target=module.ecs.aws_ecr_repository.streamlit`
   - docker build + push to ECR
   - `terraform apply` (full)
   - `aws ecs update-service --force-new-deployment` + wait services-stable
   - upload Glue scripts

## Terraform

- Remote state: S3 bucket `weatherdata-terraform-state` (dev/ and prod/ keys)
- Modules: `s3`, `iam`, `glue`, `athena`, `scheduler`, `ecs`
- `scheduler` module has `enabled` variable — set `false` in dev tfvars to pause Glue costs
- `ecs` module: ECR repo + lifecycle policy, ECS cluster, Fargate task (0.25 vCPU / 0.5 GB), ALB (HTTP port 80) with sticky sessions, IAM execution role (ECR pull + CloudWatch logs) + task role (S3 + Secrets Manager read), CloudWatch log group (7-day retention)

## Key Config

- Python 3.11, line length 100
- Test markers: `unit`, `integration`, `data_quality`, `slow`
- DuckDB version: >=0.10.0
- ECS health check: `/_stcore/health` on port 8501 (ALB target group)
- ALB idle timeout: 3600 s (keeps WebSocket connections alive)
- Streamlit config: `docker/streamlit/streamlit_config.toml` — headless, CORS off, XSRF off
- `tzdata` pip package required in container (python:3.11-slim lacks system timezone data)
