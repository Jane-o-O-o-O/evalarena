# Contributing to EvalArena

Thank you for your interest in contributing to EvalArena! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/Jane-o-O-o-O/evalarena.git
cd evalarena

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_elo.py -v

# Run with coverage
python -m pytest tests/ --cov=evalarena --cov-report=term-missing
```

## Code Style

- **Type annotations** — All functions must have type hints
- **Docstrings** — All public functions/classes must have docstrings
- **Async** — Use `async/await` for all database and API operations
- **Error handling** — Always handle errors gracefully with appropriate HTTP status codes

## Making Changes

1. Create a branch: `git checkout -b feature/my-feature`
2. Write tests first (TDD encouraged)
3. Implement your changes
4. Run tests: `python -m pytest tests/ -v`
5. Commit with a descriptive message: `feat: add my feature`
6. Push and create a Pull Request

## Commit Message Format

Use conventional commits in Chinese:

```
类型: 中文描述
```

Types:
- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation
- `test` — Tests
- `refactor` — Code refactoring
- `chore` — Maintenance

## Project Structure

```
src/evalarena/
├── api/          # FastAPI route handlers
├── core/         # ELO algorithm
├── db/           # Database models and operations
├── templates/    # Jinja2 HTML templates
├── app.py        # FastAPI application factory
└── cli.py        # Click CLI commands
tests/            # pytest test suite
```

## Reporting Issues

Please use GitHub Issues to report bugs or request features. Include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Python version and OS
