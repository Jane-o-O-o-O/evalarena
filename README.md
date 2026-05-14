# ⚔️ EvalArena

**Self-hosted LLM evaluation arena — blind side-by-side comparison with ELO rankings.**

> Like [LMSYS Chatbot Arena](https://chat.lmsys.org/), but runs on your own server. No data leaves your machine.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-317%20passed-brightgreen.svg)]()
[![PyPI](https://img.shields.io/pypi/v/evalarena?color=blue)](https://pypi.org/project/evalarena/)

### Why EvalArena?

| Feature | LMSYS Chatbot Arena | EvalArena |
|---------|-------------------|-----------|
| Self-hosted | ❌ | ✅ |
| Private data | ❌ Public | ✅ Local SQLite |
| Category leaderboards | ❌ | ✅ Coding / Writing / Reasoning |
| Head-to-Head compare | ❌ | ✅ |
| API access | Limited | ✅ Full REST API |
| Custom models | ❌ | ✅ Register any model |
| LLM auto-sampling | ❌ | ✅ OpenAI / Anthropic |
| Docker deploy | ❌ | ✅ One command |

---

## 📖 项目简介

EvalArena 是一个 LLM 评估竞技场，提供盲评侧边对比（blind side-by-side comparison）模式，让用户在不知道模型身份的情况下比较两个 LLM 的回答质量，并通过 ELO 评分系统生成可信的排行榜。灵感来源于 LMSYS Chatbot Arena。

## ✨ 核心特性

### 🎭 盲评侧边对比
- 随机分配两个匿名模型回答（随机交换 A/B 消除位置偏见）
- 用户在不知模型身份的情况下投票
- 投票后揭晓双方模型身份和评分
- 避免品牌偏见影响评估

### 📈 ELO 评分系统
- 基于 Elo rating 的模型排名（K-factor=32）
- 支持胜/负/平三种结果
- 动态更新排名，投票后即时生效
- **95% 置信区间** — 基于对战场数自动计算评分区间

### 🏷️ 模型管理
- CLI 和 API 两种注册方式
- 支持增删查模型
- **分类标签系统** — 模型可标记为 coding/writing/reasoning 等分类
- 按 ELO rating 自动排序
- **模型详情页** — 含对战历史、评分区间可视化
- **批量导入** — 支持 JSON/CSV 文件批量注册模型

### 🏆 分类排行榜
- 全局排行榜 + 按分类过滤的子排行榜
- 分类筛选下拉框
- API 支持 `?category=coding` 查询参数

### 🔍 Head-to-Head 对比
- 任意两个模型的直接胜负对比
- 可视化胜负比例条
- 支持 API 和 Web UI 两种查看方式

### 🔐 API 密钥认证
- 可选的 API 密钥认证（保护写操作）
- CLI 管理密钥（创建/列表/停用）
- GET 请求始终公开，POST/PUT/DELETE 需密钥

### 🌐 Web UI
- 暗色主题简洁对战界面
- 一键投票（A更好 / B更好 / 平局）
- **投票后揭晓模型身份** — 显示双方模型名称和评分
- 实时排行榜展示（含 95% CI + 分类标签）
- 分类筛选排行榜
- 模型详情页（对战历史 + **Chart.js 评分趋势图**）
- Head-to-Head 对比页
- **对比矩阵页** — 所有模型的逐对胜负可视化
- **投票评论展示** — 对战历史页面显示投票者评语

### 📡 RESTful API
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/models` | GET/POST | 模型管理（支持 `?category=` 过滤） |
| `/api/models/{id}` | GET/PUT/DELETE | 模型详情/更新/删除 |
| `/api/models/{id}/detail` | GET | 模型详情+对战历史 |
| `/api/models/{a}/head-to-head/{b}` | GET | Head-to-Head 对比 |
| `/api/arena` | GET/POST | 创建/查看对战 |
| `/api/arena/auto-battle` | POST | **LLM自动对战**（调用Provider API） |
| `/api/arena/{id}` | GET | 对战详情（含模型身份） |
| `/api/arena/random/pair` | GET | 随机选择两个模型 |
| `/api/vote` | POST | 提交投票（IP去重） |
| `/api/leaderboard` | GET | 排行榜（支持 `?category=` 过滤） |
| `/api/leaderboard/categories` | GET | 列出所有分类 |
| `/api/stats` | GET | 平台统计数据 |
| `/api/stats/categories` | GET | **分类统计数据** |
| `/api/stats/comparison-matrix` | GET | **模型对比矩阵** |
| `/api/battles/with-comments` | GET | **带评论的对战历史** |
| `/api/battles/search?q=` | GET | **全文搜索** |
| `/api/tournaments` | GET/POST | **锦标赛管理** |
| `/api/tournaments/{id}` | GET | **锦标赛详情+积分榜** |
| `/api/tournaments/{id}/start` | POST | 启动锦标赛 |
| `/api/tournaments/{id}/complete` | POST | 完成锦标赛 |
| `/api/streaks` | GET | **连胜追踪排行榜** |
| `/api/models/{id}/streak` | GET | 单模型连胜信息 |
| `/api/webhooks` | GET/POST | **Webhook管理** |
| `/api/webhooks/{id}` | DELETE | 删除Webhook |
| `/api/keys` | GET/POST | API 密钥管理 |
| `/api/providers` | GET | LLM Provider状态 |
| `/health` | GET | 健康检查 |

### 🔒 API 安全
- 滑动窗口速率限制（默认 60 次/分钟）
- 可选 API 密钥认证（`--api-key` 参数启用）
- 仅限制 API 端点，不影响 Web UI

### 🤖 LLM Provider 集成
- 抽象 Provider 接口，支持任何 LLM API
- 内置 OpenAI（GPT-4o 等）和 Anthropic（Claude 等）适配器
- Mock Provider 用于测试和开发
- 自动对战：`POST /api/arena/auto-battle` 自动调用两个模型的 API 生成回答
- 配置方式：设置 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` 环境变量
- 为模型设置 `provider` 和 `api_model_id` 字段即可启用自动对战

### 🌱 内置评估模板（Seed Templates）
- 16 个预置评估模板，覆盖 coding、writing、reasoning、math、general 五大类
- 一键加载：`evalarena seed-templates` 或 `evalarena seed-templates --category coding`
- API 支持：`GET /api/templates` 查看所有模板，`GET /api/templates/{id}/random-battle` 基于模板创建对战
- 模板按使用次数排序，高频模板排在前面

### 📊 模型对比矩阵
- 所有模型的逐对胜负记录可视化
- Web UI：`/compare/matrix` 页面显示绿色/红色胜率条
- API：`GET /api/stats/comparison-matrix` 返回所有模型对的 H2H 数据
- CLI：`evalarena comparison-matrix` 终端查看

### 🏆 锦标赛系统（Tournament）
- **Round-robin 循环赛** — 所有模型两两对决
- 自动赛程生成，支持积分排名
- 状态管理：pending → in_progress → completed / cancelled
- Web UI：`/tournaments` 页面
- API：`POST /api/tournaments` 创建，`GET /api/tournaments/{id}` 查看
- CLI：`evalarena create-tournament`、`evalarena list-tournaments`、`evalarena tournament-standings`

### 🔍 全文搜索
- 搜索 battles 的 prompt 和 response 内容
- Prompt 匹配优先级高于 response 匹配
- API：`GET /api/battles/search?q=keyword`
- CLI：`evalarena search-battles <query>`

### 📈 连胜追踪（Win Streak）
- 追踪每个模型的当前连胜/连败
- 记录最佳连胜和最佳连败
- API：`GET /api/streaks`、`GET /api/models/{id}/streak`
- CLI：`evalarena win-streaks`

### 🔔 Webhook 通知
- 投票后自动 POST 到注册的 URL
- 支持 HMAC 签名验证
- API：`POST /api/webhooks`、`GET /api/webhooks`、`DELETE /api/webhooks/{id}`
- CLI：`evalarena create-webhook`、`evalarena list-webhooks`

### 💾 数据备份/恢复
- 完整数据库备份到 JSON
- 从备份恢复（自动跳过重复数据）
- CLI：`evalarena backup`、`evalarena restore`

### 🐳 Docker 部署
```bash
# 一键启动
docker compose up -d

# 带环境变量
OPENAI_API_KEY=sk-xxx docker compose up -d

# 自定义端口
docker compose run -p 9090:8080 evalarena
```

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| Web 框架 | FastAPI |
| 数据库 | SQLite (aiosqlite) |
| 模板引擎 | Jinja2 |
| 测试 | pytest, pytest-asyncio, httpx |
| 包管理 | hatchling |

## 📁 项目结构

```
evalarena/
├── src/evalarena/
│   ├── __init__.py           # 版本号
│   ├── app.py                # FastAPI 应用工厂 + 速率限制 + API密钥认证
│   ├── cli.py                # CLI 入口 (click)
│   ├── api/                  # API 路由
│   │   ├── models.py         # 模型管理 + 详情 + H2H + 更新
│   │   ├── arena.py          # 竞技场对战 + 自动对战
│   │   ├── vote.py           # 投票（IP去重）
│   │   ├── leaderboard.py    # 排行榜 + 分类
│   │   ├── stats.py          # 平台统计
│   │   ├── keys.py           # API 密钥管理
│   │   └── providers.py      # LLM Provider 状态
│   ├── providers/            # LLM Provider 集成
│   │   ├── base.py           # 抽象接口 + LLMResponse
│   │   ├── registry.py       # Provider 注册表
│   │   ├── openai_provider.py # OpenAI 适配器
│   │   ├── anthropic_provider.py # Anthropic 适配器
│   │   └── mock_provider.py  # 测试用 Mock Provider
│   ├── core/
│   │   └── elo.py            # ELO 评分算法 + 置信区间
│   ├── db/
│   │   ├── database.py       # SQLite CRUD + 对战历史 + H2H + 统计 + 密钥
│   │   └── models.py         # Pydantic 数据模型
│   └── templates/            # Jinja2 模板
│       ├── base.html
│       ├── arena.html        # 投票界面 + 模型揭晓
│       ├── leaderboard.html  # 分类筛选排行榜
│       ├── model_detail.html
│       ├── compare.html
│       └── 404.html
├── tests/                    # 264 个测试用例
│   ├── test_elo.py           # ELO 算法 + CI 测试
│   ├── test_database.py      # 数据库层测试
│   ├── test_api.py           # API 集成测试
│   ├── test_categories.py    # 分类 + API密钥 + 认证测试
│   └── test_rate_limit.py    # 速率限制测试
├── pyproject.toml
└── README.md
```

## 🚀 快速开始

```bash
# 安装
git clone https://github.com/Jane-o-O-o-O/evalarena.git
cd evalarena
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 启动服务
evalarena serve --port 8080

# 启用 API 密钥认证
evalarena serve --port 8080 --api-key "your-secret-key"

# 或用 CLI 管理
evalarena add-model "GPT-4o" --category coding
evalarena add-model "Claude-3.5" --category general
evalarena list-models
evalarena list-models --category coding
```

### CLI 命令

```bash
# 模型管理
evalarena add-model <name> [--category <category>] [--provider <provider>] [--api-model-id <id>]
evalarena update-model <name> [--new-name <name>] [--category <cat>] [--provider <prov>]
evalarena list-models [--category <category>]
evalarena search-models <query>
evalarena delete-model <name> [--yes]
evalarena import-models models.json [--category general]
evalarena import-models models.csv

# LLM Provider
evalarena providers                    # 列出所有 Provider 及配置状态

# 对战和投票
evalarena battle <model_a> <model_b> --prompt "..." --response-a "..." --response-b "..."
evalarena vote <battle_id> model_a|model_b|tie
evalarena battles [--limit N] [--unvoted]

# 排行榜
evalarena export [--format json|csv] [--category <category>]

# API 密钥
evalarena create-key <name>
evalarena list-keys

# 数据库
evalarena init-db
evalarena serve [--api-key KEY]

# 种子数据和分析
evalarena seed-templates [--category <category>]  # 加载内置评估模板
evalarena comparison-matrix                         # 模型对比矩阵
evalarena category-stats                            # 分类统计

# 锦标赛
evalarena create-tournament <name> --models "A,B,C"  # 创建循环赛
evalarena list-tournaments [--status pending]          # 列出锦标赛
evalarena tournament-standings <id>                    # 查看积分榜

# 搜索和连胜
evalarena search-battles <query>                    # 全文搜索battles
evalarena win-streaks                               # 连胜排行榜

# Webhook
evalarena create-webhook <url> [--event vote]       # 注册Webhook
evalarena list-webhooks                             # 列出Webhooks

# 备份恢复
evalarena backup [--output backup.json]             # 数据备份
evalarena restore <backup.json> [--yes]             # 数据恢复
```

### API 使用示例

```bash
# 注册模型（带分类和Provider）
curl -X POST http://localhost:8080/api/models \
  -H "Content-Type: application/json" \
  -d '{"name": "GPT-4o", "category": "coding", "provider": "openai", "api_model_id": "gpt-4o"}'

# 更新模型信息
curl -X PUT http://localhost:8080/api/models/xxx \
  -H "Content-Type: application/json" \
  -d '{"category": "reasoning", "description": "Updated description"}'

# 批量导入
curl -X POST http://localhost:8080/api/models \
  -H "Content-Type: application/json" \
  -d '{"name": "Claude-3.5", "category": "writing", "provider": "anthropic", "api_model_id": "claude-3-5-sonnet-20241022"}'

# 创建对战（手动提供回答）
curl -X POST http://localhost:8080/api/arena \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "什么是递归？",
    "response_a": "递归是函数调用自身...",
    "response_b": "递归是一种编程技术...",
    "model_a_id": "xxx",
    "model_b_id": "yyy"
  }'

# 自动对战（LLM API 自动生成回答）
curl -X POST http://localhost:8080/api/arena/auto-battle \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "什么是递归？",
    "model_a_id": "xxx",
    "model_b_id": "yyy"
  }'

# 投票
curl -X POST http://localhost:8080/api/vote \
  -H "Content-Type: application/json" \
  -d '{"battle_id": "abc123", "winner": "model_a"}'

# 查看全局排行榜
curl http://localhost:8080/api/leaderboard

# 查看分类排行榜
curl http://localhost:8080/api/leaderboard?category=coding

# 列出所有分类
curl http://localhost:8080/api/leaderboard/categories

# 查看模型详情
curl http://localhost:8080/api/models/xxx/detail

# Head-to-Head 对比
curl http://localhost:8080/api/models/xxx/head-to-head/yyy

# 平台统计
curl http://localhost:8080/api/stats

# API 密钥认证（启用后）
curl -X POST http://localhost:8080/api/models \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key" \
  -d '{"name": "New-Model"}'
```

## 📄 许可证

MIT License © 2026 Jane-o-O-o-O
