# Changelog

All notable changes to EvalArena will be documented in this file.

## [0.6.0] - 2026-05-14

### Added
- **Seed prompt templates** — 16 built-in templates for coding, writing, reasoning, math, and general evaluation
- **CLI `seed-templates` command** — Load built-in templates into the database with category filtering
- **Comparison matrix API** — `GET /api/stats/comparison-matrix` for all-pairs head-to-head data
- **Comparison matrix page** — `/compare/matrix` with win rate bars for all model pairs
- **Category stats API** — `GET /api/stats/categories` with per-category model counts, ratings, battles, votes
- **CLI `comparison-matrix` command** — Show pairwise model comparison results
- **CLI `category-stats` command** — Show per-category statistics
- **Vote comments in battle history** — `/battles` page now shows voter reasoning for each battle
- **Battles-with-comments API** — `GET /api/battles/with-comments` returns voted battles with comments
- **Chart.js rating trend chart** — Model detail page uses Chart.js for interactive rating visualization with color-coded win/loss/tie points

### Fixed
- Fixed flaky test `test_get_model_trends` — now accounts for random A/B position swap in battle creation

### Changed
- Navigation bar now includes "📊 对比矩阵" (Comparison Matrix) link
- Battles page now displays vote comments alongside battle results
- Model detail page rating chart upgraded from manual canvas drawing to Chart.js with tooltips
- Version bumped to 0.6.0
- 34 new tests (264 total, all passing)

## [0.5.0] - 2026-05-13

### Added
- **Prompt template system** — CRUD API + CLI for reusable evaluation prompts
- **Auto-battle web UI** — `/auto-battle` page with model selection and template support
- **Batch battle API** — `POST /api/arena/batch` for multi-prompt evaluations
- **Vote comments** — Optional reasoning field on votes
- **Model trends API** — `GET /api/models/{id}/trends` for rating chart data
- **Battle export CLI** — `export-battles` command for JSON/CSV data export
- 41 new tests (231 total)

## [0.4.0] - 2026-05-13

### Added
- **LLM Provider framework** — Abstract provider interface with OpenAI and Anthropic adapters
- **Auto-battle** — `POST /api/arena/auto-battle` auto-samples LLM responses for blind comparison
- **Model update API** — `PUT /api/models/{id}` for partial metadata updates
- **CLI `update-model`** — Update model metadata including `--provider` and `--api-model-id`
- **CLI `providers`** — List available LLM providers and their configuration status
- **`GET /api/providers`** — API endpoint to check provider availability
- **Voter IP dedup** — Same IP cannot vote twice on the same battle
- **Dockerfile + docker-compose.yml** — One-command deployment with `docker compose up`
- **GitHub Actions CI** — Automated testing on Python 3.10/3.11/3.12
- **Mock provider** — Testing provider that returns deterministic responses

### Changed
- Models now have `provider` and `api_model_id` fields for LLM API integration
- Version bumped to 0.4.0
- 33 new tests (190 total)

## [0.3.0] - 2026-05-12

### Added
- **Rating change tracking** — BattleSummary now shows actual ELO rating delta per match
- **Landing page** — Stats overview with model count, battles, votes, and top 5 leaderboard
- **CLI `stats` command** — Display platform statistics from terminal
- **CLI `head-to-head` command** — Compare two models by name
- **CHANGELOG.md** — Project changelog
- **CONTRIBUTING.md** — Contribution guidelines

### Changed
- Refactored `app.py` to use closure pattern instead of global variable
- Version bumped to 0.3.0

## [0.2.0] - 2026-05-12

### Added
- Model category tags (coding, writing, reasoning, etc.)
- Per-category leaderboard filtering
- API key management (create, list, deactivate)
- Optional API key authentication for write operations
- CLI `vote` command for direct voting
- CLI `battles` command for battle history
- CLI `import-models` for JSON/CSV bulk import
- CLI `create-key` and `list-keys` commands
- Vote reveals model identity in Web UI
- Category filter dropdown in leaderboard page
- 16 new tests (total: 115)

## [0.1.0] - 2026-05-11

### Added
- ELO rating system with configurable K-factor
- 95% confidence intervals for ratings
- Model CRUD (create, read, delete)
- Blind side-by-side battle creation (random A/B swap)
- Vote system (model_a, model_b, tie)
- Leaderboard with ELO ranking
- Head-to-head model comparison
- Model detail page with match history
- Platform statistics API
- Web UI with dark theme
- Rate limiting middleware
- RESTful API with OpenAPI docs
- CLI with serve, init-db, add-model, list-models, export commands
