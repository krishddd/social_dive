# Social Dive — Developer Conventions

## Language & Environment
- Python 3.10+ with type hints on every function/method signature
- Rust (edition 2021) for the `_social_dive_core` extension module via PyO3/maturin
- `loguru` for all logging (never `print()` for diagnostic output)
- `rich` for all CLI terminal output
- `httpx` for Python-side HTTP requests (async-capable)
- `openai` SDK for all OpenAI-compatible API calls (NVIDIA NIM, OpenAI, MiniMax)

## Architecture Rules
- **This is a glue/routing layer, not a wrapper** — agents call upstream tools directly after setup
- Never modify upstream open-source tool source code
- Every channel must implement all four abstract methods: `can_handle()`, `read()`, `search()`, `check()`
- A broken channel must never crash the doctor report or affect other channels
- Config/credentials stored only at `~/.social-dive/config.yaml` with 0600 permissions
- Environment variables always override config file values

## Version Sync
Version string must stay in sync across:
1. `pyproject.toml` → `[project].version`
2. `social_dive/__init__.py` → `__version__`
3. `Cargo.toml` → `[package].version`
4. `tests/test_cli.py` → version assertion

## Testing
- `pytest tests/ -v` must pass before any commit
- Every channel needs: URL pattern test, mock-response parse test, error-handling test
- `test_channel_contracts.py` uses reflection to verify all Channel subclasses implement the interface
- Work on a branch, PR to main

## Code Style
- `ruff` for linting (`pyproject.toml` has the config)
- `mypy` for type checking
- Max line length: 100 characters
- Use `from __future__ import annotations` in every module
- Docstrings: Google style

## Adding a New Channel
1. Create `social_dive/channels/<name>.py`
2. Subclass `Channel`, set `name`, `tier`, `backends`
3. Implement `can_handle()`, `read()`, `search()`, `check()`
4. Decorate the class with `@register_channel`
5. Add tests in `tests/test_channels.py`
6. Auto-discovery handles the rest — no manual registration needed
