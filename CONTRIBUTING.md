# Contributing to Social Dive

We love your input! We want to make contributing to this project as easy and transparent as possible.

## Development Setup

1. Fork the repo and clone it locally.
2. Ensure you have Python 3.10+ and Rust installed.
3. Install development dependencies:
   ```bash
   pip install -e .[dev]
   ```
4. This project uses `maturin` to build the Rust extensions.

## Workflow

1. Create a branch for your feature or bugfix.
2. Make your changes.
3. Run linters and tests:
   ```bash
   ruff check .
   mypy social_dive
   pytest tests/ -v
   ```
4. Commit your changes and push to your fork.
5. Submit a pull request.

## Adding a New Channel

We encourage adding new knowledge sources! To add a new channel:
1. Create a new Python file in `social_dive/channels/`.
2. Inherit from `social_dive.channels.Channel`.
3. Implement `can_handle`, `read`, `search`, and `check`.
4. Add the `@register_channel` decorator to your class.
5. Add basic tests in `tests/test_channels.py`.

Please ensure that your channel implements gracefully degrading backends whenever possible (e.g., trying a CLI tool first, then falling back to a REST API).
