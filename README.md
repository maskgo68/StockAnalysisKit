🌐 Language: [English](README_EN.md) | 中文

# StockAnalysisKit

美股/全球股票分析工具，支持单股分析与多股对比，聚合行情数据、财务快照、估值/预测指标，并调用 AI 生成分析报告。

提供 Web UI，支持中英文切换，可本地运行或 Docker 部署。

## 设计理念

数据驱动、机构视角、对比分析、中长线投资

## 功能

### 股票数据看板

在同一页面展示四大维度数据，支持最多 10 只股票同时对比：

| 模块 | 指标 |
|------|------|
| 实时行情 | 股价、涨跌幅、总市值、成交额、PE TTM、5/20/250 日涨跌幅 |
| 最新财报 | 营收 (YoY)、利润 (YoY)、EPS、毛利率、净利率 |
| 预测与预期 | 预测 EPS (季度/年度)、下季度财报日期、EPS Surprise 历史、EPS Trend 变化 |
| 估值指标 | Forward PE、PEG、EV/EBITDA、P/S、P/B |

### AI 分析

- **财务分析** — 基于近 3 年年报 + 近 4 季度财报，分析增速、利润率、现金流、ROE 等核心指标，给出经营趋势判断
- **投资建议** — 结合大盘、板块、财务数据、新闻/研报进行综合分析；多股时自动对比，单股直接给出建议
- **目标价预测** — AI 综合估值与市场预期给出目标价参考
- **多轮追问** — 财报分析与投资建议均支持多轮对话跟进

### 其他功能

- **自选股管理** — 保存/加载自定义股票组合，支持命名与编辑
- **历史分析记录** — 每次 AI 分析结果自动存入 SQLite，按股票代码和时间分类，可回溯对比
- **投资笔记** — 按股票记录个人想法，支持 Markdown，可新增/删除
- **导出** — 数据导出为 Excel（行情/财报/预测/估值分表）、页面截屏
- **中英文切换** — 前端界面与 AI 输出语言同步切换

## 数据源

| 来源 | 用途 |
|------|------|
| [Finnhub](https://finnhub.io/) | 实时行情（优先） |
| [yfinance](https://github.com/ranaroussi/yfinance) | 行情兜底、财报数据、预测数据、AI 分析用的历史财务数据 |
| Yahoo Finance 页面爬取 | 估值指标 (Forward PE, PEG, EV/EBITDA, P/S, P/B) |
| [Exa](https://exa.ai/) / [Tavily](https://tavily.com/) | 专业搜索 API，为 AI 提供最新新闻与研报（可选） |

## 支持的 AI 供应商

| 供应商 | 说明 |
|--------|------|
| Gemini | 默认供应商，内置 Google Search 联网能力 |
| OpenAI 兼容 | 支持 OpenAI 及任何兼容 API（可自定义 Base URL） |
| Claude | Anthropic Claude 系列模型 |

- 所有 API Key 在前端页面输入，支持连接测试，配置面板可折叠

- 未配置专业搜索 API 时，自动回退到模型自带的搜索能力

## 快速开始

### Docker 运行（推荐）

**Docker一键运行**

```
docker run -d --name stockanalysiskit --restart unless-stopped -p 16888:16888 -v ./data:/app/data -v ./logs:/app/logs supergo6/stockanalysiskit:latest
```

**使用预构建镜像：**

```bash
mkdir -p data logs && docker run -d \
  --name stockanalysiskit \
  --restart unless-stopped \
  -p 16888:16888 \
  -v ./data:/app/data \
  -v ./logs:/app/logs \
  supergo6/stockanalysiskit:latest
```

或使用 docker compose：

```bash
docker compose -f docker-compose.image.yml up -d
```

**本地构建：**

```bash
docker compose up -d --build
```

### 本地运行

```bash
pip install -r requirements.txt
python app.py
```

Windows 下 `python app.py` 会自动在新终端窗口启动服务。如需在当前终端前台运行：

```bash
python app.py --serve
```

服务管理：

```bash
python app.py --status   # 查看状态
python app.py --stop     # 停止服务
```

启动后访问：`http://127.0.0.1:16888`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_PORT` | `16888` | 服务监听端口 |
| `STOCKANALYSISKIT_PORT` | `16888` | Docker 主机映射端口 |
| `STOCKANALYSISKIT_DB_PATH` | - | SQLite 文件路径 |
| `LOG_DIR` | `/app/logs` | 日志目录（Docker 建议挂载到 `./logs:/app/logs`） |
| `LOG_RETENTION_DAYS` | `3` | 日志自动清理天数 |
| `STOCKANALYSISKIT_FIN_CACHE_TTL_HOURS` | `12` | 财务数据缓存有效期（小时） |
| `GUNICORN_WORKERS` | `2` | Gunicorn worker 数 |
| `GUNICORN_THREADS` | `4` | Gunicorn 线程数 |
| `GUNICORN_TIMEOUT` | `120` | Gunicorn 请求超时（秒） |
| `AI_AUTO_CONTINUE_MAX_ROUNDS` | `64` | AI 自动续写轮数上限 |
| `NEWS_ITEMS_PER_STOCK` | `10` | 每只股票新闻抓取数（上限 20） |
| `EXTERNAL_SEARCH_ITEMS_PER_STOCK` | `10` | 每只股票外部搜索条数（上限 20） |
| `EXA_API_KEY` | - | Exa 搜索 API Key（可选） |
| `TAVILY_API_KEY` | - | Tavily 搜索 API Key（可选） |
| `DEFAULT_UI_LANGUAGE` | `zh` | 默认界面语言（`zh` / `en`） |

## 技术栈

- **后端：** Flask + Gunicorn，线程池并发抓取
- **数据：** yfinance、Finnhub API、Yahoo Finance 爬取、BeautifulSoup
- **AI：** 直接调用 Gemini / OpenAI / Claude API
- **持久化：** SQLite（自选股、分析历史、投资笔记、财务缓存）
- **前端：** 原生 HTML/CSS/JS，Markdown 渲染
- **部署：** Docker（Python 3.13-slim 基础镜像，健康检查）

## 测试

```bash
python -m pytest -q
```

## 注意事项

- 理论上支持全球大多数交易所股票，但美股效果最好

- 适合个股分析，ETF、基金效果差

- 适合中长线投资，不适合短线

- 适合有基本面支撑的大盘股，不适合概念炒作

## 感谢

本项目为vibe coding开发，感谢以下项目帮助

[openai/codex: Lightweight coding agent that runs in your terminal](https://github.com/openai/codex)

[obra/superpowers: An agentic skills framework & software development methodology that works.](https://github.com/obra/superpowers)

## 免责声明

本项目仅用于学习与信息整理，不构成任何投资建议。投资有风险，入市需谨慎！
