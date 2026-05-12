# Changelog

All notable changes to EvalArena will be documented in this file.

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
