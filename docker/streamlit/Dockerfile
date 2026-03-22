FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    streamlit>=1.35.0 \
    plotly>=5.22.0 \
    duckdb>=0.10.0 \
    python-dotenv>=1.0.0 \
    boto3>=1.34.0 \
    tzdata>=2024.1

# Pre-install the httpfs extension at build time to avoid runtime failures
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.close()"

COPY app/ ./app/
COPY scripts/ ./scripts/

RUN mkdir -p .streamlit
COPY docker/streamlit/streamlit_config.toml .streamlit/config.toml

EXPOSE 8501

CMD ["streamlit", "run", "app/dashboard.py"]
