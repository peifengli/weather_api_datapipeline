FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    streamlit>=1.35.0 \
    plotly>=5.22.0 \
    duckdb>=0.10.0 \
    python-dotenv>=1.0.0 \
    boto3>=1.34.0

# Pre-install the httpfs extension into the DuckDB extension cache at build time
# so the container never needs to download it at runtime (avoids network/write failures)
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.close()"

COPY app/ ./app/
COPY scripts/ ./scripts/

EXPOSE 8501

CMD ["streamlit", "run", "app/dashboard.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]
