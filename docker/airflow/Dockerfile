FROM apache/airflow:2.9.0-python3.11

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

USER airflow

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install Airflow providers + DBT
RUN pip install --no-cache-dir \
    apache-airflow-providers-amazon==8.19.0 \
    apache-airflow-providers-http==4.10.0 \
    dbt-core==1.7.14 \
    dbt-duckdb==1.7.3 \
    dbt-athena-community==1.7.1

WORKDIR /opt/airflow
