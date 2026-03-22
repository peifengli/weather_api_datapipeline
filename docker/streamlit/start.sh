#!/bin/sh
# Start Streamlit on internal port 8502, then Nginx on port 8501 (App Runner's target port).
# Nginx handles WebSocket upgrade headers that App Runner's proxy may strip.
streamlit run app/dashboard.py --server.port=8502 &
nginx -g "daemon off;"
