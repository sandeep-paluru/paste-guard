FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY VERSION paste-guard.toml pasteguard ./
COPY backend backend
# Data for the /demo/compare and /demo/redteam pages (they answer 404 without it)
COPY demo/compare demo/compare
COPY demo/redteam demo/redteam
COPY eval/bench_summary.json eval/bench_summary.json
COPY eval/bench/fastpath.json eval/bench/fastpath.json
COPY eval/data eval/data
ENV PG_CONFIG=/app/paste-guard.toml PG_PYTHON=python PG_MODEL_CACHE=/app/data/models PG_THREADS=1
# Bind to all interfaces inside the container; compose publishes it on 127.0.0.1 only.
CMD ["sh", "-c", "sed -i 's/^host = .*/host = \"0.0.0.0\"/' paste-guard.toml && ./pasteguard reindex && ./pasteguard serve"]
