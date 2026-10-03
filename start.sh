#!/bin/sh
set -eu
python ingest.py
uvicorn main:app --host 127.0.0.1 --port 8000 &
exec streamlit run streamlit_ui/app.py --server.address 0.0.0.0 --server.port "${PORT:-8501}" --server.headless true
