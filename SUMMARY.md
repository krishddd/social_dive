# Social Dive - Project Summary

## Overview
Social Dive is a hybrid Python/Rust CLI and library designed to provide AI coding agents (like Claude, Cursor, Windsurf, etc.) with the ability to safely and efficiently read from and search across the internet. 

Instead of being a full proxy or scraper, Social Dive acts as a capability layer—an installer, diagnostician ("doctor"), and config manager that directs agents on how to use real upstream APIs and CLIs (like `gh`, `yt-dlp`, `arxiv`, etc.).

## Architecture
- **Language:** Python 3.10+ (CLI, configuration, orchestrator) & Rust 2021 (Core parsing and I/O).
- **Core Orchestrator:** Located in `social_dive/core.py`. Dispatches URLs to the correct channel based on URL pattern matching.
- **Rust Core:** Implemented via PyO3/maturin in `src/lib.rs`. Includes a high-speed DOM walker (`html_to_markdown`) and a concurrent HTTP fetcher (`parallel_fetch`) that releases the Python GIL.
- **Configuration:** Stored securely at `~/.social-dive/config.yaml` using strict `0600` POSIX permissions to prevent credential leaks.
- **MCP Server:** FastMCP integration in `social_dive/integrations/mcp_server.py` exposing 5 core agent tools.

## Channels Implemented
1. **Academic/Scholarly:** ArXiv, PubMed, Semantic Scholar, Crossref, OpenAlex, Europe PMC, DOI Resolver.
2. **Code/Developer:** GitHub, Stack Overflow, DEV.to, Hacker News.
3. **General Web/Media:** Web fallback (Jina/Rust parser), Wikipedia, YouTube, RSS/Atom.

## CI/CD Infrastructure
- Configured via GitHub Actions in `.github/workflows/ci.yml`.
- **Matrix Testing:** Ubuntu, macOS, Windows across Python 3.10, 3.11, and 3.12.
- **Pipeline Steps:** Checkout → Rust Toolchain Setup → Python Setup → Maturin Build → Ruff Linting → Mypy Type Checking → Pytest Execution.

## Extending the Project
Adding a new channel is simple:
1. Create a new file in `social_dive/channels/`.
2. Subclass `Channel` and implement `can_handle`, `read`, `search`, and `check`.
3. Use the `@register_channel` decorator. 
The core orchestrator automatically discovers new channels using `pkgutil`.
