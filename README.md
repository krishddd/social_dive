# 🤿 Social Dive

[![CI](https://github.com/krishddd/social_dive/actions/workflows/ci.yml/badge.svg)](https://github.com/krishddd/social_dive/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/social-dive.svg)](https://badge.fury.io/py/social-dive)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Social Dive** is an AI-agent internet-access capability layer for 20+ knowledge sources. 
It acts as an installer, doctor, config tool, and execution layer that connects AI Agents (Claude Code, Cursor, Windsurf, etc.) with platforms like arXiv, GitHub, YouTube, Wikipedia, PubMed, Semantic Scholar, Hacker News, Stack Overflow, DEV.to, RSS feeds, Crossref DOIs, OpenAlex, Europe PMC, and the broader web.

> 📖 **Want to know how it works under the hood?** Read the [Project Architecture Summary](SUMMARY.md).

Built with a hybrid **Python** and **Rust** architecture, Social Dive features high-performance HTML-to-Markdown parsing and concurrent HTTP fetching without locking the Python GIL.

## Features

- **Multi-Source Read & Search:** 16+ internet sources natively supported without complex scraping tools.
- **LLM Integration:** Seamless integration with NVIDIA NIM (DeepSeek, GLM, MiniMax), OpenAI, and Anthropic.
- **MCP Server Included:** Exposes capabilities to any MCP-compatible AI agent.
- **Zero-Config Options:** Works out-of-the-box for most sources (no API keys required).
- **High Performance:** Rust core for HTML parsing and concurrent fetching.

## Installation

```bash
pip install social-dive
```

*(Optional) Install with specific LLM provider support:*
```bash
pip install "social-dive[anthropic]"
```

## Quick Start

Check system health and available channels:
```bash
social-dive doctor
```

Read content from any supported URL (returns clean Markdown). Pass several
URLs to fetch them concurrently:
```bash
social-dive read https://arxiv.org/abs/2401.12345
social-dive read https://arxiv.org/abs/2401.12345 https://github.com/psf/requests
```

Summarize a web page using an LLM:
```bash
social-dive summarize https://en.wikipedia.org/wiki/Artificial_intelligence
```

Search across academic or code sources. The JSON output includes a `skipped`
map explaining why any channel returned nothing (e.g. `rate_limited`), so you
can tell "found nothing" from "couldn't search":
```bash
social-dive search "Transformer architecture" --channels=arxiv,semantic_scholar --format=json
```

Install optional per-channel dependencies and register the agent skill
(`--dry-run` previews, `--safe` only prints instructions):
```bash
social-dive install --dry-run
social-dive skill --install
```

## Configuration

Configure your LLM provider and API keys securely:

```bash
# Set LLM provider (nvidia, openai, or anthropic)
social-dive configure llm_provider nvidia

# Set your API keys
social-dive configure nvidia_api_key "nvapi-..."
social-dive configure github_token "ghp_..."

# OpenAlex retired its free "polite pool" in Feb 2026 — a key is now
# recommended (without one the channel still works but is rate-limited).
social-dive configure openalex_api_key "..."

# View current configuration
social-dive configure --list
```

Configuration is stored securely in `~/.social-dive/config.yaml` with strict file permissions (`0600`).

You can force a specific backend per channel with a `<channel>_backend` key
(e.g. `web_backend`, `doi_resolver_backend`).

### Responsible web access

The `web` channel prefers a site's `/llms.txt` summary when present and
respects Cloudflare's Content-Signal `ai-input` opt-out in `robots.txt`,
declining to fetch content a site has marked off-limits to AI (override with
`web_ignore_ai_signals true` if you have permission).

## Model Context Protocol (MCP)

Social Dive includes a built-in MCP server so your AI agent can call its tools directly. 
Start the server using:

```bash
python -m social_dive.integrations.mcp_server
```

### MCP Tools Available:
- `read_url`: Read and extract content from any URL.
- `read_many`: Read multiple URLs concurrently, returning a JSON array.
- `search`: Search across academic, code, and web sources. *(Renamed from
  `search_sources` in 0.2.0; the old name remains as a deprecated alias for one
  release — update your MCP client config.)*
- `check_health`: Report channel availability.
- `summarize_url`: Summarize content using the configured LLM.
- `list_channels`: List all available knowledge channels.

All tools are annotated `readOnlyHint` / `openWorldHint` so MCP hosts (Claude
Code, Cursor, …) can auto-approve and parallelize them.

## Supported Channels

| Channel | Description | Tier |
|---------|-------------|------|
| `arxiv` | Academic preprints | Zero Config |
| `github` | Repositories, issues, PRs | Needs Key |
| `youtube` | Video transcripts | Zero Config |
| `wikipedia` | Encyclopedia articles | Zero Config |
| `semantic_scholar` | Academic papers | Needs Key (optional) |
| `pubmed` | Biomedical literature | Needs Key |
| `hacker_news` | Tech news + discussions | Zero Config |
| `stack_overflow` | Programming Q&A | Needs Key (optional) |
| `devto` | Developer articles | Zero Config |
| `crossref` | DOI metadata | Zero Config |
| `openalex` | Scholarly works | Needs Key |
| `europe_pmc` | Open-access papers | Needs Key |
| `rss` | RSS/Atom feeds | Zero Config |
| `doi_resolver` | DOI → full text | Zero Config |
| `web` | Catch-all web reader | Zero Config |

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
