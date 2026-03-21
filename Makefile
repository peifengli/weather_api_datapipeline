.PHONY: help up down restart logs ps \
        init-localstack \
        test test-unit test-integration test-quality test-dbt \
        lint format type-check \
        dbt-run dbt-test dbt-docs \
        tf-init tf-plan-dev tf-apply-dev tf-plan-prod tf-apply-prod \
        clean

SHELL := /bin/bash
ENV_FILE := .env
DOCKER_COMPOSE := docker compose --env-file $(ENV_FILE)
DBT_DIR := dbt
VENV := .venv
PYTHON := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

# ── Local Dev Environment ──────────────────────────────────────────────────────

up: ## Start the full local dev stack (Airflow + LocalStack + Superset)
	@cp -n $(ENV_FILE).example $(ENV_FILE) 2>/dev/null || true
	$(DOCKER_COMPOSE) up -d --build
	@echo "Waiting for LocalStack to be ready..."
	@until curl -sf http://localhost:4566/_localstack/health | grep -q '"s3": "running"'; do sleep 2; done
	@$(MAKE) init-localstack
	@echo ""
	@echo "  Airflow UI   → http://localhost:8080  (admin/admin)"
	@echo "  Superset     → http://localhost:8088  (admin/admin)"
	@echo "  LocalStack   → http://localhost:4566"
	@echo "  Flower       → http://localhost:5555"

down: ## Stop all local services
	$(DOCKER_COMPOSE) down

restart: ## Restart all services
	$(DOCKER_COMPOSE) restart

logs: ## Follow logs for all services (use svc=<name> to filter)
	$(DOCKER_COMPOSE) logs -f $(svc)

ps: ## Show running containers
	$(DOCKER_COMPOSE) ps

LOCALSTACK_ENV := AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1
LOCALSTACK_AWS := $(LOCALSTACK_ENV) aws --endpoint-url=http://localhost:4566

init-localstack: ## Bootstrap LocalStack with required AWS resources
	@echo "Creating S3 buckets in LocalStack..."
	$(LOCALSTACK_AWS) s3 mb s3://weatherdata-raw-local || true
	$(LOCALSTACK_AWS) s3 mb s3://weatherdata-processed-local || true
	$(LOCALSTACK_AWS) s3 mb s3://weatherdata-athena-results-local || true
	@echo "Creating/updating Secrets Manager entry..."
	@set -a && . ./$(ENV_FILE) && set +a && \
	  API_KEY=$${OPENWEATHERMAP_API_KEY} && \
	  if [ -z "$$API_KEY" ]; then echo "ERROR: OPENWEATHERMAP_API_KEY is not set in $(ENV_FILE)" && exit 1; fi && \
	  SECRET="{\"OPENWEATHERMAP_API_KEY\":\"$$API_KEY\"}" && \
	  $(LOCALSTACK_AWS) secretsmanager create-secret \
	    --name openweather_api_key \
	    --secret-string "$$SECRET" 2>/dev/null || \
	  $(LOCALSTACK_AWS) secretsmanager put-secret-value \
	    --secret-id openweather_api_key \
	    --secret-string "$$SECRET"
	@echo "LocalStack initialized."

# ── Testing ────────────────────────────────────────────────────────────────────

test: ## Run all tests (unit + integration + data quality)
	$(PYTEST) tests/ -m "unit or integration or data_quality" --tb=short

test-unit: ## Run unit tests only (fast, no external deps)
	$(PYTEST) tests/unit/ -m unit --tb=short -q

test-integration: ## Run integration tests (requires LocalStack running)
	$(PYTEST) tests/integration/ -m integration --tb=short

test-quality: ## Run data quality tests
	$(PYTEST) tests/data_quality/ -m data_quality --tb=short

test-dbt: ## Run DBT tests (schema + data quality)
	cd $(DBT_DIR) && dbt test --profiles-dir . --target local

test-all: test test-dbt ## Run every test suite

# ── Code Quality ───────────────────────────────────────────────────────────────

lint: ## Lint with ruff
	ruff check src/ tests/ airflow/

format: ## Format with black + ruff
	black src/ tests/ airflow/ dbt/
	ruff check --fix src/ tests/ airflow/

type-check: ## Type check with mypy
	mypy src/

pre-commit: ## Run pre-commit hooks on all files
	pre-commit run --all-files

# ── DBT ───────────────────────────────────────────────────────────────────────

dbt-deps: ## Install DBT package dependencies
	cd $(DBT_DIR) && dbt deps --profiles-dir .

dbt-run: ## Run all DBT models (local target by default)
	cd $(DBT_DIR) && dbt run --profiles-dir . --target $(DBT_TARGET)

dbt-run-prod: ## Run all DBT models against production Athena
	cd $(DBT_DIR) && dbt run --profiles-dir . --target prod

dbt-test: ## Run all DBT tests
	cd $(DBT_DIR) && dbt test --profiles-dir . --target $(DBT_TARGET)

dbt-docs: ## Generate and serve DBT docs
	cd $(DBT_DIR) && dbt docs generate --profiles-dir . --target $(DBT_TARGET)
	cd $(DBT_DIR) && dbt docs serve --profiles-dir . --port 8081

dbt-freshness: ## Check source freshness
	cd $(DBT_DIR) && dbt source freshness --profiles-dir . --target $(DBT_TARGET)

# ── Terraform ─────────────────────────────────────────────────────────────────

tf-init: ## Initialize Terraform
	cd terraform && terraform init

tf-validate: ## Validate Terraform configuration
	cd terraform && terraform validate

tf-fmt: ## Format Terraform files
	cd terraform && terraform fmt -recursive

tf-plan-dev: ## Plan Terraform for dev environment
	cd terraform && terraform plan -var-file=environments/dev.tfvars -out=tfplan-dev

tf-apply-dev: ## Apply Terraform for dev environment
	cd terraform && terraform apply tfplan-dev

tf-plan-prod: ## Plan Terraform for production
	cd terraform && terraform plan -var-file=environments/prod.tfvars -out=tfplan-prod

tf-apply-prod: ## Apply Terraform for production (requires confirmation)
	@echo "WARNING: This will apply changes to PRODUCTION. Are you sure? [y/N]"
	@read ans && [ $${ans:-N} = y ] && cd terraform && terraform apply tfplan-prod

tf-destroy-dev: ## Destroy dev infrastructure (use with caution)
	cd terraform && terraform destroy -var-file=environments/dev.tfvars

# ── Utilities ─────────────────────────────────────────────────────────────────

clean: ## Remove build artifacts and cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	find . -name ".coverage" -delete 2>/dev/null || true
	find . -name "coverage.xml" -delete 2>/dev/null || true
	rm -rf dbt/target dbt/logs dbt/.user.yml 2>/dev/null || true
	@echo "Cleaned."
