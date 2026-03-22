# Tri-State Weather API Data Pipeline

A production-grade data pipeline that fetches hourly weather data for 19 cities across New York, New Jersey, and Connecticut, processes it through AWS, and serves an interactive dashboard.

---

## Architecture

```
OpenWeatherMap API
        │
        ▼
 EventBridge Scheduler (every 15 min)
        │
        ▼
  AWS Lambda  ──► Glue Workflow
                      │
                      ├─► fetch_weather (Glue job)
                      │        └─► s3://weatherdata-raw-{env}/
                      │
                      └─► process_weather (Glue job)
                               └─► s3://weatherdata-processed-{env}/
                                          │
                               ┌──────────┴──────────┐
                               ▼                     ▼
                          DBT models            Streamlit Dashboard
                        (Athena/DuckDB)       (AWS App Runner, prod)
                               │
                          AWS Athena
                    (SQL queries via Glue Catalog)
```

**Local development** mirrors production using LocalStack (mock AWS) + Airflow for orchestration.

---

## Tech Stack

| Layer | Local | Production |
|---|---|---|
| Orchestration | Apache Airflow (CeleryExecutor) | AWS EventBridge + Lambda |
| Ingestion | Python (direct) | AWS Glue (PySpark) |
| Storage | LocalStack S3 | AWS S3 |
| Transformation | DBT + DuckDB | DBT + AWS Athena |
| Secrets | LocalStack Secrets Manager | AWS Secrets Manager |
| Dashboard | Streamlit (localhost:8501) | Streamlit on AWS App Runner |
| Infra-as-code | — | Terraform |
| CI/CD | — | GitHub Actions |

---

## Project Layout

```
├── app/
│   └── dashboard.py          # Streamlit dashboard (local + prod)
├── airflow/
│   └── dags/
│       └── weather_pipeline.py  # Airflow DAG (local dev)
├── dbt/                       # DBT models (staging → marts)
├── docker/
│   ├── airflow/Dockerfile
│   ├── streamlit/Dockerfile
│   └── superset/Dockerfile
├── scripts/
│   └── s3_to_duckdb.py        # Sync S3 processed data → local DuckDB
├── src/
│   ├── glue/
│   │   ├── fetch_weather.py   # Glue job: fetch from OpenWeatherMap
│   │   └── process_weather.py # Glue job: transform raw JSON
│   └── lambda/
│       └── trigger_pipeline.py # Lambda: trigger Glue workflow
├── terraform/
│   ├── modules/
│   │   ├── apprunner/         # App Runner + ECR module
│   │   ├── athena/
│   │   ├── glue/
│   │   ├── iam/
│   │   ├── s3/
│   │   └── scheduler/         # EventBridge + Lambda trigger
│   └── environments/
│       ├── dev/               # Dev Terraform config
│       └── prod/              # Prod Terraform config
├── tests/
│   ├── unit/
│   ├── integration/           # Requires LocalStack
│   └── data_quality/          # Great Expectations
├── .github/workflows/
│   ├── ci.yml                 # Lint + test on every PR
│   └── cd.yml                 # Deploy to dev → prod on merge to main
└── docker-compose.yml         # Full local dev stack
```

---

## Local Development

### Prerequisites

- Docker + Docker Compose
- Python 3.11
- An [OpenWeatherMap API key](https://openweathermap.org/api) (free tier works)

### Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/your-org/weather_api_datapipeline.git
cd weather_api_datapipeline

# 2. Copy env file and add your API key
cp .env.example .env
# Edit .env → set OPENWEATHERMAP_API_KEY=your_key_here

# 3. Create Python virtualenv (for local tools)
python3.11 -m venv .venv
pip install -r requirements.txt -r requirements-dev.txt

# 4. Start the full local stack
make up
```

This starts Airflow, LocalStack (mock AWS), Superset, and Streamlit. LocalStack is auto-bootstrapped with S3 buckets and Secrets Manager entries.

### Local service URLs

| Service | URL | Credentials |
|---|---|---|
| Airflow UI | http://localhost:8080 | admin / admin |
| Streamlit Dashboard | http://localhost:8501 | — |
| Superset | http://localhost:8088 | admin / admin |
| LocalStack | http://localhost:4566 | — |
| Flower (Celery) | http://localhost:5555 | — |

### Running the pipeline locally

```bash
# Trigger the DAG manually in Airflow UI, or:
# In Airflow UI → DAGs → weather_pipeline → ▶ Trigger

# After data lands in LocalStack S3, sync it to local DuckDB:
make refresh-db

# The Streamlit dashboard auto-reloads from DuckDB (TTL 5 min)
# Or open http://localhost:8501 and click "Refresh Data"
```

### Running the dashboard standalone (no Docker)

```bash
make refresh-db    # sync S3 → data/weather.db
make dashboard     # opens http://localhost:8501
```

### Stopping

```bash
make down                  # stop everything
make down-scheduler        # stop only Airflow scheduler/worker (keep LocalStack)
```

---

## Testing

```bash
make test              # all tests (unit + integration + data quality)
make test-unit         # fast, no external deps
make test-integration  # requires LocalStack running (make up first)
make test-quality      # Great Expectations data quality checks
make test-dbt          # DBT schema + data tests
make test-all          # everything
```

---

## Code Quality

```bash
make lint        # Ruff
make format      # Black + Ruff autofix
make type-check  # MyPy
make pre-commit  # all hooks
```

---

## DBT

```bash
make dbt-run           # run all models (local DuckDB by default)
make dbt-test          # run schema + data quality tests
make dbt-docs          # generate + serve docs at http://localhost:8081
make dbt-run-prod      # run against production Athena
```

---

## Deploying to AWS

### Prerequisites

- Terraform >= 1.6
- AWS CLI configured with sufficient permissions
- S3 bucket `weatherdata-terraform-state` (remote state backend)

### Manual deploy

```bash
# Dev
make tf-plan-dev
make tf-apply-dev

# Prod (prompts for confirmation)
make tf-plan-prod
make tf-apply-prod
```

### Infrastructure created per environment

| Resource | Dev | Prod |
|---|---|---|
| S3 buckets (raw, processed, athena-results) | ✅ | ✅ |
| Glue jobs (fetch + process) | ✅ | ✅ |
| EventBridge scheduler (15 min) | ✅ (disableable) | ✅ |
| Lambda trigger | ✅ | ✅ |
| Athena workgroup + database | ✅ | ✅ |
| Secrets Manager (API key) | ✅ | ✅ |
| ECR repository (Streamlit image) | — | ✅ |
| App Runner service (dashboard) | — | ✅ |

### Cost saving — disable dev scheduling when prod is live

```bash
make disable-dev-scheduling   # stops hourly Glue jobs in dev (~$0 running cost)
make enable-dev-scheduling    # re-enable when needed
```

---

## CI/CD (GitHub Actions)

### On every pull request → `ci.yml`

1. **Lint** — Ruff + Black + MyPy
2. **Unit tests** — pytest, no external deps
3. **Integration tests** — pytest against mocked AWS (moto)
4. **Data quality tests** — Great Expectations
5. **Terraform validate** — both dev and prod environments

### On merge to `main` → `cd.yml`

```
CI gate (all tests pass)
    │
    ▼
Deploy → dev  (automatic)
    │  - terraform apply
    │  - upload Glue scripts to S3
    │
    ▼
Smoke tests → dev
    │
    ▼
Deploy → prod  ← manual approval required (GitHub Environment)
    │  1. terraform apply -target ECR  (create repo)
    │  2. docker build + push to ECR
    │  3. terraform apply (full)       (App Runner picks up image)
    │  4. upload Glue scripts to S3
    ▼
✅ Dashboard live at App Runner URL
```

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `AWS_DEPLOY_ROLE_DEV` | OIDC IAM role ARN for dev deployments |
| `AWS_DEPLOY_ROLE_PROD` | OIDC IAM role ARN for prod deployments |

Prod deployments require a reviewer configured in the **prod** GitHub Environment settings.

---

## Dashboard Features

The Streamlit dashboard covers all 19 tri-state cities:

| Section | Description |
|---|---|
| **Weather Map** | PyDeck scatter map — colour = temperature, opacity = population |
| **Current Conditions** | Per-city cards with temp, feels-like, humidity, wind |
| **Regional Snapshot** | Max/min/avg temp + wind KPIs with hour-over-hour delta |
| **Temperature Tracking** | Dual line chart (temp + feels-like) + City Advisor |
| **City Advisor** | Seasonal activity suggestions filtered by weather severity |
| **Conditions Distribution** | Horizontal bar chart of weather condition frequency |
| **City Comparison** | Box plot showing temp range (min/avg/max) per city |
| **Hourly Detail** | Expandable raw data table |

The sidebar has a 24-hour time slider with ▶ Play animation and city/state filters.

---

## Environment Variables

Copy `.env.example` to `.env`. Key variables:

```bash
OPENWEATHERMAP_API_KEY=   # required
WEATHER_LAT=40.7143       # default: NYC
WEATHER_LON=-74.006
ENVIRONMENT=local         # local | dev | prod

# S3 buckets (auto-suffixed by environment)
S3_RAW_BUCKET=weatherdata-raw-local
S3_PROCESSED_BUCKET=weatherdata-processed-local

# Airflow
AIRFLOW__CORE__FERNET_KEY=   # generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
