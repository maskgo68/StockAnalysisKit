FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    APP_PORT=16888 \
    LOG_DIR=/app/logs \
    LOG_RETENTION_DAYS=3 \
    STOCKANALYSISKIT_FIN_CACHE_TTL_HOURS=12 \
    GUNICORN_WORKERS=2 \
    GUNICORN_THREADS=4 \
    GUNICORN_TIMEOUT=120 \
    AI_AUTO_CONTINUE_MAX_ROUNDS=64 \
    AI_CLAUDE_MAX_TOKENS=64000 \
    NEWS_ITEMS_PER_STOCK=10 \
    EXTERNAL_SEARCH_ITEMS_PER_STOCK=10 \
    EXA_API_KEY= \
    TAVILY_API_KEY= \
    DEFAULT_UI_LANGUAGE=zh

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/logs

EXPOSE 16888

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,sys,urllib.request; port=os.getenv('APP_PORT','16888'); urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=4); sys.exit(0)"

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${APP_PORT} --workers ${GUNICORN_WORKERS} --threads ${GUNICORN_THREADS} --timeout ${GUNICORN_TIMEOUT} app:app"]
