# StockAnalysisKit

StockAnalysisKit is a Flask-based web app for U.S. stock comparison and AI-assisted analysis.
It combines quote data, financial metrics, forecast/valuation data, and AI reasoning into one workflow.

## What It Does

- Compare up to 10 U.S. stock symbols in one request
- Show real-time market metrics and recent financials
- Show prediction and valuation metrics separately
- Generate AI financial analysis and AI investment advice
- Support follow-up Q&A on both analysis flows
- Save/load watchlists with SQLite persistence
- Export comparison results to Excel (`realtime`, `financial`, `prediction`, `valuation`, `meta`)

## Tech Stack

- Backend: Flask (`app.py`)
- Data and AI orchestration: `stock_service.py`
- Persistence (watchlist + financial cache): `persistence.py` (SQLite)
- Frontend: `templates/index.html`, `static/app.js`, `static/styles.css`
- Runtime: Gunicorn + Docker

## API Overview

- `GET /api/compare`
- `POST /api/export-excel`
- `POST /api/financial-analysis`
- `POST /api/financial-analysis-followup`
- `POST /api/ai-analysis`
- `POST /api/ai-analysis-followup`
- `POST /api/target-price-analysis`
- `POST /api/test-config`
- `GET /api/watchlist`
- `POST /api/watchlist`
- `GET /api/watchlist/<id>`
- `PATCH /api/watchlist/<id>`
- `DELETE /api/watchlist/<id>`

## Quick Start (Local, Non-Docker)

```bash
pip install -r requirements.txt
python app.py --serve
```

Open: `http://127.0.0.1:16888`

Service commands:

```bash
python app.py --status
python app.py --stop
```

## One-Line VPS Deploy (Prebuilt DockerHub Image)

Use the prebuilt image directly (no build step on VPS):

```bash
docker run -d --name stockanalysiskit --restart unless-stopped -p 16888:16888 -v ./data:/app/data -v ./logs:/app/logs supergo6/stockanalysiskit:latest
```

Open: `http://<your-vps-ip>:16888`

## Update Container to Latest Image

```bash
docker pull supergo6/stockanalysiskit:latest
docker rm -f stockanalysiskit
docker run -d --name stockanalysiskit --restart unless-stopped -p 16888:16888 -v ./data:/app/data -v ./logs:/app/logs supergo6/stockanalysiskit:latest
```

## Docker Compose

Run with prebuilt image:

```bash
docker compose -f docker-compose.image.yml up -d
```

Run by building locally:

```bash
docker compose up -d --build
```

## Key Environment Variables

- `APP_PORT` (default `16888`)
- `STOCKANALYSISKIT_DB_PATH` (default `/app/data/stockanalysiskit.db`)
- `STOCKANALYSISKIT_FIN_CACHE_TTL_HOURS` (default `12`)
- `GUNICORN_WORKERS` (default `2`)
- `GUNICORN_THREADS` (default `4`)
- `GUNICORN_TIMEOUT` (default `120`)
- `NEWS_ITEMS_PER_STOCK` (default `10`)
- `EXTERNAL_SEARCH_ITEMS_PER_STOCK` (default `10`)
- `EXA_API_KEY` (optional)
- `TAVILY_API_KEY` (optional)
- `AI_AUTO_CONTINUE_MAX_ROUNDS` (default `64`)
- `AI_CLAUDE_MAX_TOKENS` (default `64000`)

## Test

```bash
python -m pytest -q
```

## Build and Push Docker Image (Maintainer)

```bash
docker build -t supergo6/stockanalysiskit:latest .
docker push supergo6/stockanalysiskit:latest
```

Optional version tag:

```powershell
$tag = "$(Get-Date -Format yyyyMMdd)-$(git rev-parse --short HEAD)"
docker tag supergo6/stockanalysiskit:latest "supergo6/stockanalysiskit:$tag"
docker push "supergo6/stockanalysiskit:$tag"
```

## Notes

- Do not hardcode API keys in source code.
- This project is for research and information organization, not investment advice.
