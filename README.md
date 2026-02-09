# 美股分析助手 (Stock Analysis Assistant)

美股分析助手是一个基于 Flask 的 Web 应用，用于单股分析和多股对比分析。它聚合实时行情、财务数据、估值指标、新闻与外部搜索结果，并结合大模型输出财务分析与投资建议。

本项目强调两件事：
- 结构化数据先行：先把关键指标整理清楚，再做 AI 判断
- 分析可追问：财务分析和投资建议都支持多轮追问

## 核心能力

- 单股分析与多股对比（最多 10 只）
- 四大数据面板同页展示
  - 实时行情
  - 最新财务数据
  - 预测
  - 估值
- 预期与财报兑现子模块
  - 财报 beat/miss 与历史 EPS surprise
  - EPS Trend（7/30/60/90 天）
- AI 财务分析（支持本地规则版 + AI 增强版）
- AI 投资建议（单股给建议、多股给排序与对比）
- Exa / Tavily 外部搜索增强
- 多轮追问（财务分析、投资建议各自独立上下文）
- 自选组合管理（保存、加载、重命名、删除）
- 财务缓存持久化（SQLite）
- 导出 Excel、页面截图

## 技术架构

- 后端：Flask
- 数据抓取：requests + BeautifulSoup + yfinance
- 存储：SQLite（watchlist + financial cache）
- 前端：原生 HTML/CSS/JavaScript
- 容器化：Docker + docker compose

### 数据源策略

- 实时行情：Finnhub 优先，缺失时回退 yfinance
- 最新财务与预测字段：yfinance
- 估值字段：Yahoo Finance quoteSummary / 页面解析
- 新闻：Finnhub company-news，失败时回退 Yahoo RSS
- 外部搜索：Exa / Tavily（可选）

## 目录结构

- `app.py`：Flask 入口、API 路由、服务启动/状态/停止
- `stock_service.py`：数据抓取、清洗、分析、AI 调用
- `persistence.py`：SQLite 持久化与财务缓存
- `templates/index.html`：页面结构
- `static/app.js`：前端状态与交互逻辑
- `static/styles.css`：页面样式
- `tests/`：pytest 测试用例

## 快速开始

### 1) 本地运行

```bash
pip install -r requirements.txt
python app.py
```

访问地址：`http://127.0.0.1:16888`

### 2) Docker 运行

```bash
docker compose up -d --build
docker compose logs -f
docker compose down
```

### 3) VPS 一键部署

```bash
curl -fsSL https://raw.githubusercontent.com/maskgo68/StockAnalysisKit/main/scripts/vps-one-click-deploy.sh | sudo bash
```

默认会部署到 `/opt/stockanalysiskit`，端口 `16888`。

可选自定义参数（仍然是一条命令）：

```bash
curl -fsSL https://raw.githubusercontent.com/maskgo68/StockAnalysisKit/main/scripts/vps-one-click-deploy.sh | sudo REPO_URL=https://github.com/maskgo68/StockAnalysisKit.git DEPLOY_BRANCH=main APP_DIR=/opt/stockanalysiskit STOCKCOMPARE_PORT=18080 bash
```

## 服务管理命令

```bash
python app.py --status   # 查看服务状态
python app.py --stop     # 停止服务
python app.py --serve    # 当前终端前台运行
python app.py            # 默认启动（Windows 下可拉起新终端）
```

## 配置说明

### 前端可配置项

- Finnhub API Key
- AI Provider：OpenAI 兼容 / Gemini / Claude
- AI 模型名
- AI API Key
- OpenAI 兼容 Base URL
- Exa API Key（可选）
- Tavily API Key（可选）

### 常用环境变量

- `STOCKCOMPARE_DB_PATH`：SQLite 文件路径
- `STOCKCOMPARE_FIN_CACHE_TTL_HOURS`：财务缓存有效期（小时）
- `NEWS_ITEMS_PER_STOCK`：每只股票新闻条数（1-20）
- `EXTERNAL_SEARCH_ITEMS_PER_STOCK`：每只股票外部搜索条数（1-20）
- `EXA_API_KEY` / `TAVILY_API_KEY`：外部搜索 Key（可选）
- `AI_AUTO_CONTINUE_MAX_ROUNDS`：AI 自动续写轮数上限
- `AI_CLAUDE_MAX_TOKENS`：Claude 单次 `max_tokens`

## API 概览

### 数据与分析

- `GET /api/compare`
- `POST /api/export-excel`
- `POST /api/financial-analysis`
- `POST /api/ai-analysis`
- `POST /api/financial-analysis-followup`
- `POST /api/ai-analysis-followup`
- `POST /api/test-config`

### 自选组合

- `GET /api/watchlist`
- `POST /api/watchlist`
- `GET /api/watchlist/<id>`
- `PATCH /api/watchlist/<id>`
- `DELETE /api/watchlist/<id>`

## 测试

```bash
python -m pytest -q
```

## 安全与使用建议

- 不要在代码中硬编码 API Key
- 建议仅在本地可信环境保存配置
- 本工具用于研究与信息整理，不构成投资建议

