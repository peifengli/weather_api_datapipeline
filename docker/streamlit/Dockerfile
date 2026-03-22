FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    streamlit>=1.35.0 \
    plotly>=5.22.0 \
    duckdb>=0.10.0 \
    python-dotenv>=1.0.0 \
    boto3>=1.34.0

COPY app/ ./app/
COPY scripts/ ./scripts/

EXPOSE 8501

CMD ["streamlit", "run", "app/dashboard.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
