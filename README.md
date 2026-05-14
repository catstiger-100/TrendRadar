# TrendRadar 热点雷达

期货资讯聚合与 AI 解读系统。抓取多平台热榜和 RSS 订阅，通过关键词过滤、AI 自动解读、多渠道推送，帮助期货从业者快速掌握市场动态。

---

## 目录

- [技术架构](#技术架构)
- [部署说明](#部署说明)
  - [Docker 部署（推荐）](#docker-部署推荐)
  - [本地运行](#本地运行)
- [配置说明](#配置说明)
  - [数据源](#数据源)
  - [关键词配置](#关键词配置)
  - [推送通知](#推送通知)
  - [AI 功能](#ai-功能)
  - [调度系统](#调度系统)
  - [存储配置](#存储配置)
  - [高级参数](#高级参数)
- [管理控制台](#管理控制台)
- [MCP 服务](#mcp-服务)

---

## 技术架构

### 系统组成

```
TrendRadar
├── trendradar/          # 核心 Python 包
│   ├── core/            # 调度、分析、关键词匹配
│   ├── crawler/         # 平台爬虫（财联社、金十、新浪等）
│   ├── ai/              # AI 解读（新闻解读 + 态势分析）
│   ├── notification/    # 推送渠道（飞书、Telegram、邮件等）
│   ├── storage/         # 存储层（SQLite / PostgreSQL / S3）
│   └── admin_server.py  # 管理 API 服务
├── mcp_server/          # MCP 协议服务（供 AI 客户端调用）
├── console/             # Vue 3 管理控制台
└── config/              # 配置文件目录
```

### 技术栈

| 层次 | 技术 |
|------|------|
| 后端运行时 | Python 3.10+，单进程多线程 |
| AI 接口 | LiteLLM（统一适配 100+ 提供商） |
| 数据库 | PostgreSQL（Docker 部署）/ SQLite（本地运行） |
| 前端控制台 | Vue 3 + Element Plus + Vite |
| 容器化 | Docker Compose（三服务：postgres / trendradar / trendradar-mcp） |
| MCP 服务 | FastMCP，提供 20+ 工具供 AI 客户端查询 |

### 数据流

```
平台热榜 / RSS 订阅
        ↓ 爬虫抓取（每 3 分钟，可配置）
   news_articles 表
        ↓ 关键词匹配（Aho-Corasick 风格正则联合匹配）
   match_words 字段
        ↓ AI 新闻解读（后台 worker 队列，可配置并发）
   ai_interpret_result / news_article_ai_symbols
        ↓ 定时推送（调度系统控制时间窗口）
   飞书 / Telegram / 邮件 / ...
```

### 关键词匹配机制

`frequency_words.txt` 定义关键词组，每组一行，`|` 分隔同义词：

```
黄金|Gold|AU
原油|WTI|布伦特
美联储|Fed|FOMC
```

匹配时将所有关键词编译为单个正则联合式（长词优先），对标题做一次扫描，结果写入 `match_words TEXT[]` 字段。匹配到任意关键词的新闻才会进入推送报告。

### AI 解读架构

- **快速模型**（`AI_FAST`）：用于单条新闻解读，后台 worker 队列处理，默认 3 个 worker，2 个并发 AI 请求。输出：一句话摘要 + 相关期货品种（方向/强度）。
- **推理模型**（`AI_REASONING`）：用于每小时态势分析，聚合 24 小时新闻数据，输出宏观市场判断。
- 两个模型均通过管理控制台独立配置，支持 DeepSeek、OpenAI、Gemini、Claude、Ollama 等。

---

## 部署说明

### Docker 部署（推荐）

**前置条件**：Docker 和 Docker Compose

**1. 克隆仓库**

```bash
git clone https://github.com/sansan0/TrendRadar.git
cd TrendRadar
```

**2. 配置环境变量（可选）**

```bash
cp docker/.env.example docker/.env
# 编辑 docker/.env，填写通知渠道的 webhook 等敏感信息
```

也可以直接编辑 `config/config.yaml`，敏感信息建议通过环境变量传入。

**3. 启动服务**

```bash
# 使用预构建镜像（推荐）
docker compose -f docker/docker-compose.yml up -d

# 或本地构建
docker compose -f docker/docker-compose-build.yml up -d
```

**4. 访问控制台**

浏览器打开 `http://localhost:8080`

**服务说明**

| 服务 | 端口 | 说明 |
|------|------|------|
| trendradar | 8080 | 主服务（爬虫 + 推送 + 管理 API） |
| trendradar-mcp | 3333 | MCP 服务（供 AI 客户端调用） |
| postgres | 5432 | 数据库（仅本机可访问） |

**数据持久化**

- 数据库数据：Docker volume `pgdata`
- 配置文件：挂载自 `./config`（宿主机目录）
- 输出文件：挂载自 `./output`（宿主机目录）

**连接本地 Ollama**

容器内通过 `host.docker.internal` 访问宿主机服务，docker-compose 已配置 `extra_hosts`。在 AI 模型管理中将 API Base 设为 `http://host.docker.internal:11434` 即可。

**常用命令**

```bash
# 查看日志
docker logs -f trendradar

# 重启服务
docker compose -f docker/docker-compose.yml restart trendradar

# 停止所有服务
docker compose -f docker/docker-compose.yml down

# 更新镜像
docker compose -f docker/docker-compose.yml pull
docker compose -f docker/docker-compose.yml up -d
```

---

### 本地运行

**前置条件**：Python 3.10+，推荐使用 [uv](https://github.com/astral-sh/uv)

```bash
# 安装依赖
uv sync
# 或
pip install -r requirements.txt

# 运行
uv run trendradar
# 或
python -m trendradar
```

本地运行默认使用 SQLite，数据存储在 `output/` 目录。

---

## 配置说明

所有配置集中在 `config/config.yaml`。管理控制台提供可视化编辑界面，修改后实时生效（无需重启）。

### 数据源

**热榜平台**（`platforms`）

```yaml
platforms:
  enabled: true
  sources:
    - id: "cls-hot"
      name: "财联社热门"
      enabled: true
    - id: "jin10-futures"
      name: "金十期货"
      enabled: true
    # 其他平台...
```

支持的平台 ID：`cls-hot`、`jin10-futures`、`jin10`、`sina-finance-7x24`、`toutiao`、`baidu`、`wallstreetcn-hot`、`thepaper` 等。

**RSS 订阅**（`rss`）

```yaml
rss:
  enabled: true
  freshness_filter:
    enabled: true
    max_age_days: 3       # 过滤超过 3 天的旧文章
  feeds:
    - id: "yahoo-finance"
      name: "WSJ Markets"
      url: "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"
      enabled: true
      max_age_days: 0     # 0 = 不过滤，推送所有文章
```

### 关键词配置

编辑 `config/frequency_words.txt`，每行一个关键词组，`|` 分隔同义词：

```
# 贵金属
黄金|Gold|AU|黄金期货
白银|AG|银价

# 能源
原油|WTI|布伦特|SC
天然气|LNG

# 宏观
美联储|Fed|FOMC|加息|降息
CPI|通胀|通货膨胀
```

- `#` 开头为注释行，作为分组标题显示
- 同一行的词视为同义词，匹配任意一个即命中该组
- 关键词区分大小写，建议同时写中英文变体

### 推送通知

在 `config/config.yaml` 的 `notification` 段配置，或通过管理控制台的「通知渠道」页面配置。

```yaml
notification:
  enabled: true
  channels:
    feishu:
      webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/..."
    telegram:
      bot_token: "123456:ABC..."
      chat_id: "-100..."
    email:
      from: "sender@example.com"
      password: "授权码"
      to: "receiver@example.com"
    # 其他渠道...
```

**多账号**：用分号分隔多个 webhook，如 `"url1;url2"`。

**支持渠道**：飞书、钉钉、企业微信（群机器人/个人微信应用）、Telegram、Email（自动识别 SMTP）、ntfy、Bark（iOS）、Slack、通用 Webhook（Discord/Matrix/IFTTT 等）。

### AI 功能

**基础模型配置**（`ai`）

```yaml
ai:
  model: "deepseek/deepseek-chat"   # provider/model_name 格式
  api_key: ""                        # 或通过环境变量 AI_API_KEY
  api_base: ""                       # 自定义端点（可选）
  temperature: 1.0
  max_tokens: 5000
  timeout: 120
```

模型格式遵循 LiteLLM 规范：

| 提供商 | 示例 |
|--------|------|
| DeepSeek | `deepseek/deepseek-chat` |
| OpenAI | `openai/gpt-4o` |
| Google | `gemini/gemini-2.5-flash` |
| Anthropic | `anthropic/claude-3-5-sonnet` |
| 本地 Ollama | `ollama_chat/qwen2.5:7b` |
| OpenAI 兼容接口 | `openai/model-name`（配合 `api_base`） |

**AI 分析**（`ai_analysis`）

```yaml
ai_analysis:
  enabled: true
  language: "Chinese"
  max_news_for_analysis: 150    # 参与分析的新闻数量上限（影响 token 消耗）
  include_rss: false
  include_standalone: true
  include_rank_timeline: true   # 传递完整排名时间线，消耗更多 token 但分析更精准
```

**AI 新闻解读**（管理控制台配置）

在控制台「AI 模型管理」页面分别配置快速模型（新闻解读）和推理模型（态势分析）。支持独立配置不同的模型和参数。

开启「自动解读」后，新抓取的新闻会自动进入解读队列，结果展示在「资讯」页面的 AI 摘要列。

**Ollama 本地模型**

1. 在控制台「AI 模型管理」选择 Provider 为 Ollama
2. API Base 填写 `http://host.docker.internal:11434`（Docker 部署）或 `http://localhost:11434`（本地运行）
3. 填写模型名称，如 `qwen2.5:7b`
4. API Key 留空（本地模型不需要）

### 调度系统

调度系统控制何时推送、何时 AI 分析、使用哪种报告模式。

```yaml
schedule:
  enabled: true
  preset: "morning_evening"   # 预设模板
```

**预设模板**

| 模板 | 说明 |
|------|------|
| `always_on` | 全天候，有新增即推送 |
| `morning_evening` | 全天推送 + 晚间当日汇总（推荐） |
| `office_hours` | 工作日三段式（到岗/午间/收工），周末增量推送 |
| `night_owl` | 午后速览 + 深夜全天汇总 |
| `custom` | 完全自定义，编辑 `config/timeline.yaml` |

**报告模式**（`report.mode`）

| 模式 | 说明 |
|------|------|
| `daily` | 当日汇总，显示当天所有匹配新闻 |
| `current` | 当前榜单，只显示当前在榜新闻 |
| `incremental` | 增量监控，只推送新出现的匹配新闻 |

开启调度系统后，报告模式由当前时间段的配置决定，`report.mode` 被覆盖。

### 存储配置

```yaml
storage:
  backend: "auto"    # auto | local | remote
  formats:
    sqlite: true
    html: true       # 邮件推送必须开启
  local:
    data_dir: "output"
    retention_days: 0    # 0 = 永久保留
```

**远程存储（S3 兼容）**：支持 Cloudflare R2、阿里云 OSS、腾讯云 COS、AWS S3、MinIO。

```yaml
  remote:
    endpoint_url: "https://<account_id>.r2.cloudflarestorage.com"
    bucket_name: "trendradar"
    access_key_id: ""
    secret_access_key: ""
```

### 高级参数

```yaml
advanced:
  crawler:
    crawl_interval_minutes: 3    # 抓取频率（分钟）：1/3/5/10/15/30
    request_interval: 2000       # 请求间隔（毫秒）

  console:
    opinion_page_size: 200       # 资讯列表单次加载条数（10-500）
    opinion_max_load_count: 2000 # 累计最多加载条数（10-10000）

  weight:
    rank: 0.6        # 排名权重
    frequency: 0.3   # 频次权重
    hotness: 0.1     # 热度权重
```

---

## 管理控制台

Docker 部署后访问 `http://localhost:8080`，提供以下功能：

**资讯（Opinion）**

- 展示所有抓取的新闻，支持关键词搜索、来源过滤、时间筛选
- 列表视图和卡片视图切换
- 下拉到底自动加载更多（每次 200 条，最多 2000 条，可在系统设置调整）
- 显示 AI 解读摘要、关联期货品种、多空方向和强度
- 支持手动触发单条新闻的 AI 解读

**AI 态势分析**

- 展示最新一次宏观态势分析结果
- 手动触发重新分析

**AI 模型管理**

- 分别配置快速模型（新闻解读）和推理模型（态势分析）
- 支持 DeepSeek、OpenAI、Gemini、Claude、Ollama 等 Provider
- 连接测试功能
- 开关自动解读

**系统设置**

- 抓取频率配置
- 资讯列表加载参数
- 其他运行参数

**配置编辑**

- `config.yaml` 可视化编辑
- `frequency_words.txt` 关键词编辑
- `timeline.yaml` 时间线编辑

---

## MCP 服务

MCP（Model Context Protocol）服务运行在端口 3333，供 Claude Desktop、Cherry Studio 等 AI 客户端调用，让 AI 助手能直接查询 TrendRadar 的新闻数据。

**连接配置**（以 Claude Desktop 为例）

```json
{
  "mcpServers": {
    "trendradar": {
      "url": "http://localhost:3333/sse"
    }
  }
}
```

**主要工具**

| 工具 | 说明 |
|------|------|
| `get_latest_news` | 获取最新新闻 |
| `search_news` | 按关键词搜索 |
| `get_trending_topics` | 获取热门话题 |
| `analyze_topic_trend` | 分析话题趋势 |
| `get_latest_rss` | 获取最新 RSS 文章 |
| `generate_summary_report` | 生成汇总报告 |
| `send_notification` | 触发推送通知 |

完整工具列表和参数说明见 [README-MCP-FAQ.md](README-MCP-FAQ.md)。

---

## 环境变量

Docker 部署时可通过环境变量覆盖配置，避免将敏感信息写入配置文件：

| 变量 | 说明 |
|------|------|
| `AI_API_KEY` | AI 模型 API Key |
| `AI_MODEL` | AI 模型名称 |
| `AI_API_BASE` | AI API 端点 |
| `FEISHU_WEBHOOK_URL` | 飞书 Webhook |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID |
| `DINGTALK_WEBHOOK_URL` | 钉钉 Webhook |
| `WEWORK_WEBHOOK_URL` | 企业微信 Webhook |
| `EMAIL_FROM` / `EMAIL_PASSWORD` / `EMAIL_TO` | 邮件配置 |
| `PG_HOST` / `PG_DB` / `PG_USER` / `PG_PASSWORD` | PostgreSQL 连接 |
| `WEBSERVER_PORT` | 管理控制台端口（默认 8080） |
| `CRON_SCHEDULE` | 外部 cron 频率（默认 `*/30 * * * *`） |
| `OLLAMA_NUM_CTX` | Ollama 上下文窗口大小（默认 8192） |

---

## License

[GPL-3.0](LICENSE)
