# ⚔️ EvalArena

> LLM 评估竞技场 — 侧边对比模型评估，支持人类偏好评分（类似 LMSYS Chatbot Arena）

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📖 项目简介

EvalArena 是一个 LLM 评估竞技场，提供盲评侧边对比（blind side-by-side comparison）模式，让用户在不知道模型身份的情况下比较两个 LLM 的回答质量，并通过 ELO 评分系统生成可信的排行榜。灵感来源于 LMSYS Chatbot Arena。

## ✨ 核心特性

### 🎭 盲评侧边对比
- 随机分配两个匿名模型回答
- 用户在不知模型身份的情况下投票
- 避免品牌偏见影响评估

### 📈 ELO 评分系统
- 基于 Elo rating 的模型排名
- 支持置信区间计算
- 动态更新排名

### 🏷️ 分类评估
- 按任务类别分组评估（编程、写作、推理等）
- 分类别排行榜
- 交叉类别综合评分

### 🌐 Web UI 投票界面
- 简洁直观的对比界面
- 一键投票
- 实时排行榜展示

### 🔗 排行榜 API
- RESTful API 获取排行榜数据
- 支持分页和筛选
- JSON/CSV 导出

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python 3.10+ |
| Web 框架 | FastAPI |
| 数据库 | SQLite |
| 模板引擎 | Jinja2 |
| 测试 | pytest, httpx |

## 📁 项目结构

```
evalarena/
├── src/
│   └── evalarena/
│       ├── __init__.py
│       ├── app.py              # FastAPI 应用
│       ├── cli.py              # CLI 入口
│       ├── api/                # API 路由
│       │   ├── __init__.py
│       │   ├── arena.py        # 竞技场端点
│       │   ├── vote.py         # 投票端点
│       │   ├── leaderboard.py  # 排行榜端点
│       │   └── models.py       # 模型管理端点
│       ├── core/               # 核心逻辑
│       │   ├── __init__.py
│       │   ├── elo.py          # ELO 评分系统
│       │   ├── matcher.py      # 模型匹配器
│       │   └── sampler.py      # 采样策略
│       ├── db/                 # 数据库
│       │   ├── __init__.py
│       │   ├── database.py     # 数据库连接
│       │   ├── models.py       # 数据模型
│       │   └── migrations/     # 数据库迁移
│       └── templates/          # Jinja2 模板
│           ├── base.html
│           ├── arena.html
│           └── leaderboard.html
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_arena.py
│   ├── test_elo.py
│   ├── test_leaderboard.py
│   └── test_vote.py
├── examples/
├── pyproject.toml
└── README.md
```

## 🚀 安装

```bash
git clone https://github.com/Jane-o-O-o-O/evalarena.git
cd evalarena

python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 📖 使用方法

### CLI 命令

```bash
# 启动评估竞技场
evalarena serve --port 8080

# 初始化数据库
evalarena init-db

# 导出排行榜
evalarena export --format csv --output leaderboard.csv
```

### Web 访问

```bash
# 访问竞技场
open http://localhost:8080/arena

# 查看排行榜
open http://localhost:8080/leaderboard
```

### API 使用

```python
import requests

# 获取排行榜
response = requests.get("http://localhost:8080/api/leaderboard")
print(response.json())

# 提交投票
response = requests.post("http://localhost:8080/api/vote", json={
    "battle_id": "abc123",
    "winner": "model_a",  # model_a, model_b, tie
})
```

## 🗺️ 路线图

- [ ] **v0.1.0** — 基础框架：FastAPI 应用、SQLite 数据库
- [ ] **v0.2.0** — ELO 评分系统
- [ ] **v0.3.0** — Web UI 投票界面
- [ ] **v0.4.0** — 分类评估与分类排行榜
- [ ] **v0.5.0** — 排行榜 API 与导出
- [ ] **v1.0.0** — 生产就绪发布

## 📄 许可证

MIT License © 2026 Jane-o-O-o-O
