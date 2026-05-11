# ⚔️ EvalArena

> LLM 评估竞技场 — 盲评侧边对比模型评估，支持人类偏好评分（类似 LMSYS Chatbot Arena）

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📖 项目简介

EvalArena 是一个 LLM 评估竞技场，提供盲评侧边对比（blind side-by-side comparison）模式，让用户在不知道模型身份的情况下比较两个 LLM 的回答质量，并通过 ELO 评分系统生成可信的排行榜。灵感来源于 LMSYS Chatbot Arena。

## ✨ 核心特性

### 🎭 盲评侧边对比
- 随机分配两个匿名模型回答（随机交换 A/B 消除位置偏见）
- 用户在不知模型身份的情况下投票
- 避免品牌偏见影响评估

### 📈 ELO 评分系统
- 基于 Elo rating 的模型排名（K-factor=32）
- 支持胜/负/平三种结果
- 动态更新排名，投票后即时生效
- **95% 置信区间** — 基于对战场数自动计算评分区间

### 🏷️ 模型管理
- CLI 和 API 两种注册方式
- 支持增删查模型
- 按 ELO rating 自动排序
- **模型详情页** — 含对战历史、评分区间可视化

### 🔍 Head-to-Head 对比
- 任意两个模型的直接胜负对比
- 可视化胜负比例条
- 支持 API 和 Web UI 两种查看方式

### 🌐 Web UI
- 暗色主题简洁对战界面
- 一键投票（A更好 / B更好 / 平局）
- 实时排行榜展示（含 95% CI）
- 模型详情页（对战历史 + 评分区间）
- Head-to-Head 对比页

### 📡 RESTful API
| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/models` | GET/POST | 模型管理 |
| `/api/models/{id}/detail` | GET | 模型详情+对战历史 |
| `/api/models/{a}/head-to-head/{b}` | GET | Head-to-Head 对比 |
| `/api/arena` | GET/POST | 创建/查看对战 |
| `/api/vote` | POST | 提交投票 |
| `/api/leaderboard` | GET | 排行榜查询 |
| `/api/stats` | GET | 平台统计数据 |
| `/health` | GET | 健康检查 |

### 🔒 API 安全
- 滑动窗口速率限制（默认 60 次/分钟）
- 仅限制 API 端点，不影响 Web UI

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
│   ├── app.py                # FastAPI 应用工厂 + 速率限制
│   ├── cli.py                # CLI 入口 (click)
│   ├── api/                  # API 路由
│   │   ├── models.py         # 模型管理 + 详情 + H2H
│   │   ├── arena.py          # 竞技场对战
│   │   ├── vote.py           # 投票
│   │   ├── leaderboard.py    # 排行榜
│   │   └── stats.py          # 平台统计
│   ├── core/
│   │   └── elo.py            # ELO 评分算法 + 置信区间
│   ├── db/
│   │   ├── database.py       # SQLite CRUD + 对战历史 + H2H + 统计
│   │   └── models.py         # Pydantic 数据模型
│   └── templates/            # Jinja2 模板
│       ├── base.html
│       ├── arena.html
│       ├── leaderboard.html
│       ├── model_detail.html
│       ├── compare.html
│       └── 404.html
├── tests/                    # 99 个测试用例
│   ├── test_elo.py           # ELO 算法 + CI 测试
│   ├── test_database.py      # 数据库层测试
│   ├── test_api.py           # API 集成测试
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

# 或用 CLI 管理
evalarena add-model "GPT-4o"
evalarena add-model "Claude-3.5"
evalarena list-models
```

### API 使用示例

```bash
# 注册模型
curl -X POST http://localhost:8080/api/models -H "Content-Type: application/json" -d '{"name": "GPT-4o"}'

# 创建对战
curl -X POST http://localhost:8080/api/arena -H "Content-Type: application/json" -d '{
  "prompt": "什么是递归？",
  "response_a": "递归是函数调用自身...",
  "response_b": "递归是一种编程技术...",
  "model_a_id": "xxx",
  "model_b_id": "yyy"
}'

# 投票
curl -X POST http://localhost:8080/api/vote -H "Content-Type: application/json" -d '{
  "battle_id": "abc123",
  "winner": "model_a"
}'

# 查看排行榜
curl http://localhost:8080/api/leaderboard

# 查看模型详情
curl http://localhost:8080/api/models/xxx/detail

# Head-to-Head 对比
curl http://localhost:8080/api/models/xxx/head-to-head/yyy

# 平台统计
curl http://localhost:8080/api/stats
```

## 📄 许可证

MIT License © 2026 Jane-o-O-o-O
