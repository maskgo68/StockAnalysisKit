# stockcompare-codex

一个面向美股对比分析的本地 Web 工具，支持多股票并排对比、AI 投资建议、Excel 导出和页面截屏下载。

## 项目总结

本项目是一个 Flask + 原生前端实现的轻量应用，核心目标是把多只美股的关键信息放在同一页面做横向对比，并给出 AI 视角的综合建议。

- 第 1/2 部分数据来自 Finnhub（行情、财务）
- 第 3 部分数据来自 Yahoo Finance 页面解析（估值/预测）
- 支持最多 10 只股票并发抓取（线程池，最大 8 并发）
- 无数据库，实时请求、内存处理

## 功能清单

- 多股票管理：添加、删除、去重、限制最多 10 只
- 一键刷新：拉取并展示三类数据
- 三类对比表：
  - 目前行情：股价、涨跌幅、总市值、成交额、PE TTM、5 日/20 日涨跌幅
  - 历史财务：营收、利润（含 YoY）、EPS、毛利率、净利率
  - 预测估值：Forward PE、PEG、预测 EPS（含 YoY）
- AI 综合建议：
  - 支持 `openai`（兼容接口）、`gemini`、`claude`
  - Markdown 输出并前端安全渲染
  - 自动续写（当模型因长度截断时最多继续 8 轮）
- 配置测试：可测试 Finnhub 与 AI 配置可用性
- 结果导出：
  - Excel（`realtime` / `financial` / `forecast` / `meta` 四个 sheet）
  - 页面截屏 PNG（客户端 `html2canvas`）

## 技术架构

- 后端：`Flask`（`app.py`）
- 服务层：`stock_service.py`
- 前端：`templates/index.html` + `static/app.js` + `static/styles.css`
- 采集与解析：`requests` + `BeautifulSoup` + `lxml`
- 导出：`pandas` + `openpyxl`

## 快速开始

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 启动项目

```bash
python app.py
```

打开：`http://127.0.0.1:5000`

说明：在 Windows 下直接运行 `python app.py` 时，程序默认会在新终端窗口启动服务。

### 3) 页面使用流程

1. 填写 `Finnhub API Key` 并测试配置
2. 添加股票代码（如 `NVDA, AAPL, MSFT`）
3. 点击“刷新数据”查看三类对比表
4. 按需点击“生成 AI 综合建议”
5. 导出 Excel 或截屏

## Docker 部署（VPS 一键）

### 方式 1：已在项目目录

```bash
docker compose up -d --build
```

访问：`http://服务器IP:5000`

### 方式 2：新 VPS 从 GitHub 一键拉起

```bash
git clone https://github.com/hidenmaskvip/stockcompare.git
cd stockcompare
docker compose up -d --build
```

常用运维命令：

```bash
docker compose ps
docker compose logs -f
docker compose pull
docker compose up -d
docker compose down
```

## API 简要说明

- `GET /api/compare?symbols=NVDA,AAPL`
  - Header: `X-Finnhub-Api-Key`
  - 返回股票对比数据
- `POST /api/export-excel`
  - Body: `symbols`, `finnhub_api_key`
  - 返回 Excel 文件流
- `POST /api/ai-analysis`
  - Body: `symbols`, `stocks`(可选), `provider`, `api_key`, `model`, `base_url`(可选)
  - 返回 AI Markdown 分析
- `POST /api/test-config`
  - `target=finnhub` 或 `target=ai`
  - 返回配置可用性检测结果

## 数据口径与降级策略

- 金额字段统一为十亿美元（`B USD`），百分比统一 `%`，多数数值保留两位小数
- 缺失值统一返回 `null`，前端显示为 `--`，不做臆造
- Finnhub 某些套餐若无 K 线权限，会降级使用 Yahoo Chart 补齐：
  - 5 日/20 日涨跌幅
  - 成交额估算
- 新闻优先 Finnhub，失败则回退 Yahoo RSS

## 项目结构

```text
stockcompare-codex/
├─ app.py                  # Flask 入口与接口编排
├─ stock_service.py        # 数据抓取、清洗、AI 调用核心逻辑
├─ requirements.txt
├─ Dockerfile
├─ docker-compose.yml
├─ .dockerignore
├─ templates/
│  └─ index.html           # 页面骨架
└─ static/
   ├─ app.js               # 前端交互与渲染
   └─ styles.css
```

## 依赖版本

- Flask==3.1.0
- gunicorn==23.0.0
- pandas==2.2.3
- requests==2.32.3
- beautifulsoup4==4.12.3
- lxml==5.3.0
- openpyxl==3.1.5

## 已知限制

- 强依赖外部接口质量与限流策略，响应时间会随网络波动
- Yahoo 页面结构如变更，预测估值抓取可能失效
- AI 结论仅供研究参考，不构成投资建议
