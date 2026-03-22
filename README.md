# Tri-State Weather Data Pipeline

---

## Dashboard Highlights

Live weather intelligence for **19 cities across New York, New Jersey, and Connecticut** — refreshed every 30 minutes, served from AWS.

### What you see

| Section | What it shows |
|---|---|
| **Weather Map** | Temperature-coloured scatter map; dot size scales with city population |
| **Current Conditions** | Per-city cards — temp, feels-like, humidity, wind, sky condition |
| **Regional Snapshot** | Max / min / avg KPIs across the tri-state region with hour-over-hour deltas |
| **Temperature Tracking** | Dual-line chart (actual + feels-like) for up to 3 cities over the past 24 h |
| **City Advisor** | Activity suggestions per city filtered by live weather severity (severe / poor / ok) — considers rain, snow, wind, humidity, and temperature |
| **Conditions Distribution** | Horizontal bar chart of sky-condition frequency across all cities |
| **City Comparison** | Box plot of 24 h temperature range (min / avg / max) per city |
| **Hourly Detail** | Full raw data table, filterable by city and time |

**Sidebar controls:** state filter, city multi-select, 24 h time slider with ▶ Play animation.

**Cities covered:**
New York City, Buffalo, Rochester, Yonkers, Syracuse, Albany, White Plains *(NY)* ·
Newark, Jersey City, Paterson, Elizabeth, Edison, Trenton *(NJ)* ·
Bridgeport, New Haven, Stamford, Hartford, Waterbury, Norwalk *(CT)*

---

## Architecture

```
OpenWeatherMap API
        │
        ▼
EventBridge Scheduler (every 30 min)
        │
        ▼
  AWS Lambda  ──► Glue Workflow
                      │
                      ├─► fetch_weather (Glue/PySpark)
                      │        └─► s3://weatherdata-raw-{env}/
                      │
                      └─► process_weather (Glue/PySpark)
                               └─► s3://weatherdata-processed-{env}/
                                          │
                               ┌──────────┴──────────┐
                               ▼                     ▼
                          DBT models          Streamlit Dashboard
                        (Athena/DuckDB)   (ECS Fargate + ALB, prod)
                               │                     │
                          AWS Athena          DuckDB httpfs
                    (SQL via Glue Catalog)   reads S3 directly
```

**Local development** mirrors production using LocalStack (mock AWS) + Airflow.

---

## Tech Stack

| Layer | Local | Production |
|---|---|---|
| Orchestration | Apache Airflow (CeleryExecutor) | AWS EventBridge + Lambda |
| Ingestion | Python (direct) | AWS Glue (PySpark) |
| Storage | LocalStack S3 | AWS S3 |
| Transformation | DBT + DuckDB | DBT + AWS Athena |
| Secrets | LocalStack Secrets Manager | AWS Secrets Manager |
| Dashboard | Streamlit (localhost:8501) | Streamlit on ECS Fargate + ALB |
| Container Registry | — | AWS ECR |
| Infra-as-code | — | Terraform |
| CI/CD | — | GitHub Actions |

---

## Project Layout

```
├── app/
│   └── dashboard.py              # Streamlit dashboard (local + prod)
├── airflow/
│   └── dags/
│       └── weather_pipeline.py   # Airflow DAG (local dev)
├── dbt/                          # DBT models (staging → marts)
├── docker/
│   ├── airflow/Dockerfile
│   ├── streamlit/Dockerfile      # python:3.11-slim + streamlit/plotly/duckdb/boto3
│   └── superset/Dockerfile
├── scripts/
│   └── s3_to_duckdb.py           # Sync S3 processed data → local DuckDB
├── src/
│   ├── glue/
│   │   ├── fetch_weather.py      # Glue job: fetch from OpenWeatherMap
│   │   └── process_weather.py    # Glue job: validate + enrich raw JSON → Parquet
│   └── lambda/
│       └── trigger_pipeline.py   # Lambda: start Glue workflow
├── terraform/
│   ├── modules/
│   │   ├── ecs/                  # ECS Fargate + ALB + ECR + IAM
│   │   ├── athena/
│   │   ├── glue/
│   │   ├── iam/
│   │   ├── s3/
│   │   └── scheduler/            # EventBridge + Lambda trigger
│   └── environments/
│       ├── dev/
│       └── prod/
├── tests/
│   ├── unit/
│   ├── integration/              # Requires LocalStack
│   └── data_quality/
├── .github/workflows/
│   ├── ci.yml                    # Lint + test on every PR
│   └── cd.yml                    # Deploy dev → prod on merge to main
└── docker-compose.yml            # Full local dev stack
```

---

## Local Development

### Prerequisites

- Docker + Docker Compose
- Python 3.11
- An [OpenWeatherMap API key](https://openweathermap.org/api) (free tier)

### Setup

```bash
# 1. Clone
git clone https://github.com/your-org/weather_api_datapipeline.git
cd weather_api_datapipeline

# 2. Add your API key
cp .env.example .env
# Edit .env → OPENWEATHERMAP_API_KEY=your_key_here

# 3. Install Python deps (for local tooling)
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 4. Start the full stack
make up
```

Starts Airflow, LocalStack, Superset, and Streamlit. LocalStack is auto-bootstrapped with S3 buckets and Secrets Manager.

### Local service URLs

| Service | URL | Credentials |
|---|---|---|
| Airflow UI | http://localhost:8080 | admin / admin |
| Streamlit | http://localhost:8501 | — |
| Superset | http://localhost:8088 | admin / admin |
| LocalStack | http://localhost:4566 | — |
| Flower (Celery) | http://localhost:5555 | — |

### Running the pipeline locally

```bash
# Trigger via Airflow UI → DAGs → weather_pipeline → ▶ Trigger
# Then sync S3 data into the local DuckDB file:
make refresh-db

# Dashboard auto-reloads every 5 min, or hit "Refresh Data" in the sidebar
```

### Stopping

```bash
make down               # stop everything
make down-scheduler     # stop Airflow scheduler/worker only (keep LocalStack + Streamlit)
```

---

## Testing

```bash
make test              # unit + integration + data quality
make test-unit         # fast, no external deps
make test-integration  # requires LocalStack running (make up first)
make test-dbt          # DBT schema + data tests
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
make dbt-run          # run all models (local DuckDB)
make dbt-test         # schema + data quality tests
make dbt-docs         # serve docs at http://localhost:8081
make dbt-run-prod     # run against production Athena
```

---

## Deploying to AWS

### Prerequisites

- Terraform >= 1.6
- AWS CLI with sufficient permissions
- S3 bucket `weatherdata-terraform-state` (remote state backend)

### Infrastructure per environment

| Resource | Dev | Prod |
|---|---|---|
| S3 buckets (raw, processed, athena-results) | ✅ | ✅ |
| Glue jobs (fetch + process) | ✅ | ✅ |
| EventBridge scheduler (30 min) | ✅ (disableable) | ✅ |
| Lambda trigger | ✅ | ✅ |
| Athena workgroup + database | ✅ | ✅ |
| Secrets Manager (API key) | ✅ | ✅ |
| ECR repository | — | ✅ |
| ECS Fargate cluster + service | — | ✅ |
| Application Load Balancer | — | ✅ |

### Cost saving — disable dev scheduling when prod is live

```bash
make disable-dev-scheduling   # stop Glue runs in dev AWS environment
make enable-dev-scheduling    # re-enable
```

---

## CI/CD (GitHub Actions)

### On every PR → `ci.yml`

1. Lint — Ruff + Black + MyPy
2. Unit tests
3. Integration tests (moto)
4. Data quality tests
5. Terraform validate (dev + prod)

### On merge to `main` → `cd.yml`

```
CI gate (all tests pass)
    │
    ▼
Deploy → dev  (automatic)
    │  terraform apply + upload Glue scripts to S3
    │
    ▼
Smoke tests → dev
    │
    ▼
Deploy → prod  ← manual approval (GitHub Environment)
    │  1. Destroy old App Runner resources (migration, idempotent)
    │  2. terraform apply -target ECR   (create repo first)
    │  3. docker build + push to ECR
    │  4. terraform apply (full)        (ECS picks up new image)
    │  5. ecs wait services-stable      (ALB health check passes)
    │  6. upload Glue scripts to S3
    ▼
✅ Dashboard live at ALB URL
```

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `AWS_DEPLOY_ROLE_DEV` | OIDC IAM role ARN for dev deployments |
| `AWS_DEPLOY_ROLE_PROD` | OIDC IAM role ARN for prod deployments |

Prod deployments require a reviewer in the **prod** GitHub Environment settings.

---

## Environment Variables

Copy `.env.example` to `.env`:

```bash
OPENWEATHERMAP_API_KEY=   # required
ENVIRONMENT=local         # local | dev | prod

# S3 (auto-suffixed by environment)
S3_RAW_BUCKET=weatherdata-raw-local
S3_PROCESSED_BUCKET=weatherdata-processed-local

# Airflow
AIRFLOW__CORE__FERNET_KEY=   # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
