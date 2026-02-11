# StockAnalysisKit

A US/global stock analysis tool that supports single-stock analysis and multi-stock comparison. It aggregates market data, financial snapshots, and valuation/forecast metrics, and uses AI to generate analysis reports.

Provides a Web UI with Chinese/English switching, and supports local run or Docker deployment.

## Design Principles

Data-driven, institutional perspective, comparative analysis, medium/long-term investing.

## Features

### Stock Data Dashboard

Shows four major data dimensions on one page, with support for comparing up to 10 stocks at once:

| Module | Metrics |
|------|------|
| Real-time market data | Price, change %, market cap, turnover, PE TTM, 5/20/250-day change % |
| Latest financials | Revenue (YoY), profit (YoY), EPS, gross margin, net margin |
| Forecasts & expectations | Forecast EPS (quarterly/annual), next earnings date, EPS surprise history, EPS trend changes |
| Valuation metrics | Forward PE, PEG, EV/EBITDA, P/S, P/B |

### AI Analysis

- **Financial analysis** - Based on the latest 3 annual reports + latest 4 quarterly reports, analyzes growth, margins, cash flow, ROE, and other core metrics, then provides operating trend judgment.
- **Investment advice** - Combines macro/sector context, financial data, and news/research reports for comprehensive analysis; auto-compares in multi-stock mode, and gives direct recommendations in single-stock mode.
- **Target price forecast** - AI combines valuation and market expectations to provide target price references.
- **Multi-turn follow-up** - Both financial analysis and investment advice support follow-up conversations.

### Other Features

- **Watchlist management** - Save/load custom stock groups, with naming and editing support.
- **Analysis history** - Every AI analysis result is automatically stored in SQLite, categorized by symbol and time for traceable comparison.
- **Investment notes** - Record personal ideas by symbol, Markdown supported, with create/delete.
- **Export** - Export data to Excel (separate sheets for market/financial/forecast/valuation) and capture page screenshots.
- **Chinese/English switching** - Frontend UI language and AI output language switch together.

## Data Sources

| Source | Purpose |
|------|------|
| [Finnhub](https://finnhub.io/) | Real-time market data (preferred) |
| [yfinance](https://github.com/ranaroussi/yfinance) | Market-data fallback, financial data, forecast data, and historical financial context for AI analysis |
| Yahoo Finance page scraping | Valuation metrics (Forward PE, PEG, EV/EBITDA, P/S, P/B) |
| [Exa](https://exa.ai/) / [Tavily](https://tavily.com/) | Professional search APIs that provide latest news and research for AI (optional) |

## Supported AI Providers

| Provider | Description |
|--------|------|
| Gemini | Default provider, with built-in Google Search capability |
| OpenAI-compatible | Supports OpenAI and any compatible API (custom Base URL supported) |
| Claude | Anthropic Claude model family |

- All API keys are entered on the frontend page, support connectivity testing, and the config panel is collapsible.
- If external search APIs are not configured, it automatically falls back to the model's built-in search capability.

## Quick Start

### Docker Run (Recommended)

**One-command Docker run**

```bash
docker run -d --name stockanalysiskit --restart unless-stopped -p 16888:16888 -v ./data:/app/data -v ./logs:/app/logs supergo6/stockanalysiskit:latest
```

**Use prebuilt image:**

```bash
mkdir -p data logs && docker run -d \
  --name stockanalysiskit \
  --restart unless-stopped \
  -p 16888:16888 \
  -v ./data:/app/data \
  -v ./logs:/app/logs \
  supergo6/stockanalysiskit:latest
```

Or use docker compose:

```bash
docker compose -f docker-compose.image.yml up -d
```

**Build locally:**

```bash
docker compose up -d --build
```

### Run Locally

```bash
pip install -r requirements.txt
python app.py
```

On Windows, `python app.py` starts the service in a new terminal window automatically. To run in the current terminal foreground:

```bash
python app.py --serve
```

Service management:

```bash
python app.py --status   # check status
python app.py --stop     # stop service
```

After startup, visit: `http://127.0.0.1:16888`

## Environment Variables

| Variable | Default | Description |
|------|--------|------|
| `APP_PORT` | `16888` | Service listening port |
| `STOCKANALYSISKIT_PORT` | `16888` | Docker host mapped port |
| `STOCKANALYSISKIT_DB_PATH` | - | SQLite file path |
| `LOG_DIR` | `/app/logs` | Log directory (for Docker, mount `./logs:/app/logs`) |
| `LOG_RETENTION_DAYS` | `3` | Days to retain logs before auto cleanup |
| `STOCKANALYSISKIT_FIN_CACHE_TTL_HOURS` | `12` | Financial cache TTL (hours) |
| `GUNICORN_WORKERS` | `2` | Number of Gunicorn workers |
| `GUNICORN_THREADS` | `4` | Number of Gunicorn threads |
| `GUNICORN_TIMEOUT` | `120` | Gunicorn request timeout (seconds) |
| `AI_AUTO_CONTINUE_MAX_ROUNDS` | `64` | Max rounds for AI auto-continue |
| `NEWS_ITEMS_PER_STOCK` | `10` | News items fetched per stock (max 20) |
| `EXTERNAL_SEARCH_ITEMS_PER_STOCK` | `10` | External search items per stock (max 20) |
| `EXA_API_KEY` | - | Exa search API key (optional) |
| `TAVILY_API_KEY` | - | Tavily search API key (optional) |
| `DEFAULT_UI_LANGUAGE` | `zh` | Default UI language (`zh` / `en`) |

## Tech Stack

- **Backend:** Flask + Gunicorn, concurrent fetch via thread pool.
- **Data:** yfinance, Finnhub API, Yahoo Finance scraping, BeautifulSoup.
- **AI:** Direct Gemini / OpenAI / Claude API calls.
- **Persistence:** SQLite (watchlists, analysis history, investment notes, financial cache).
- **Frontend:** Vanilla HTML/CSS/JS with Markdown rendering.
- **Deployment:** Docker (Python 3.13-slim base image with health check).

## Testing

```bash
python -m pytest -q
```

## Notes

- In theory it supports most global exchanges, but works best for US stocks.
- Better suited for individual stock analysis; weaker for ETFs/funds.
- Better for medium/long-term investing, not short-term trading.
- Better for large-cap stocks with fundamental support, not concept/speculative momentum plays.

## Thanks

This project was developed via vibe coding. Thanks to:

[openai/codex: Lightweight coding agent that runs in your terminal](https://github.com/openai/codex)

[obra/superpowers: An agentic skills framework & software development methodology that works.](https://github.com/obra/superpowers)

## Disclaimer

This project is for learning and information organization only, and does not constitute investment advice. Investing involves risk; please be prudent.
