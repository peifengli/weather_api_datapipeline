FROM python:3.11-slim

# Nginx handles WebSocket upgrade headers before traffic reaches Streamlit.
# Streamlit listens on 8502 (internal); Nginx listens on 8501 (App Runner target port).
RUN apt-get update && apt-get install -y --no-install-recommends nginx && rm -rf /var/lib/apt/lists/*

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

# Nginx config: WebSocket-aware reverse proxy on :8501 → Streamlit on :8502
COPY docker/streamlit/nginx.conf /etc/nginx/nginx.conf

# Streamlit config: headless, CORS off, XSRF off
RUN mkdir -p .streamlit
COPY docker/streamlit/streamlit_config.toml .streamlit/config.toml

# Entrypoint: start Streamlit in background, then Nginx in foreground
COPY docker/streamlit/start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8501

CMD ["/start.sh"]
