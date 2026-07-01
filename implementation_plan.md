# Social Dive — Implementation Plan

**An AI-agent internet-access capability layer (installer + doctor + config tool) for 20+ knowledge sources, built with Python + Rust hybrid architecture and pluggable LLM backends.**

Social Dive is a from-scratch successor to Agent Reach. Like Agent Reach, it's a *glue/routing layer* — agents call upstream tools directly after setup. Unlike Agent Reach, it adds **LLM-powered content summarization/extraction**, a **Rust performance core**, and focuses on **knowledge-oriented** sources (research, code, articles) rather than social-media scraping.

---

## User Review Required

> [!IMPORTANT]
> **LLM Backend Strategy**: You mentioned GLM-5.1 and MiniMax as primary development backends via NVIDIA. Research shows GLM-5.2 (June 2026) is now the current flagship. The plan uses a provider-agnostic adapter that works with NVIDIA NIM (GLM-5.x, MiniMax-M3, DeepSeek, Mistral), OpenAI, and Anthropic — all via the OpenAI SDK's `base_url` swapping. Please confirm this approach.

> [!IMPORTANT]
> **Rust Scope Decision**: The plan proposes Rust for two specific hot-path modules (HTML→Markdown parser, concurrent HTTP fetcher) via PyO3/maturin. The rest stays in Python. This keeps complexity manageable while delivering real performance gains on the paths that matter. An alternative would be a Rust CLI binary called via subprocess — simpler to build but harder to integrate. Please confirm the PyO3 approach.

> [!WARNING]
> **Platform ToS Risk**: This plan explicitly **avoids** cookie-based/session-hijacking scrapers for social platforms (Twitter, Reddit, Instagram, LinkedIn). We focus on **API-blessed and open-access** sources only. This means fewer platforms than Agent Reach but zero ban-risk. If you want to add social scrapers later, that's a separate phase.

## Open Questions

1. **NVIDIA API key scope** — Will you provide one API key for development, or should the tool support users bringing their own keys? (Plan assumes: tool ships with user-provided key support, you provide yours for dev/testing.)

2. **Agent skill registration** — Do you want skill-file registration for specific agents (Claude, Cursor, etc.) in Phase 1, or is CLI + MCP enough to start?

3. **Windows-first vs. cross-platform** — Your environment is Windows. Should we prioritize Windows-native paths (PowerShell installer, Windows credential store) or build cross-platform from day one? (Plan assumes: cross-platform from day one, tested on Windows.)

4. **Offline/caching mode** — Should fetched content be cached locally for offline access? (Plan includes a simple file-based cache, confirm if you want something more sophisticated like SQLite.)

---

## Architecture Overview

```
social_dive/                         ← Python package root
├── pyproject.toml                   ← Package config (maturin build backend)
├── Cargo.toml                       ← Rust workspace root
├── src/                             ← Rust source (compiled to _social_dive_core Python module)
│   └── lib.rs                       ← PyO3 module: html_to_markdown(), parallel_fetch()
├── social_dive/                     ← Python package
│   ├── __init__.py                  ← Version + public API
│   ├── cli.py                       ← CLI entry point (argparse or typer)
│   ├── core.py                      ← SocialDive orchestrator class
│   ├── config.py                    ← Secure YAML config store (~/.social-dive/config.yaml)
│   ├── doctor.py                    ← Health-check aggregator
│   ├── probe.py                     ← Real-execution backend prober
│   ├── llm/                         ← LLM backend abstraction
│   │   ├── __init__.py
│   │   ├── base.py                  ← Abstract LLMProvider interface
│   │   ├── nvidia.py                ← NVIDIA NIM (GLM, MiniMax, DeepSeek, Mistral)
│   │   ├── openai_provider.py       ← OpenAI native
│   │   └── anthropic_provider.py    ← Anthropic native
│   ├── channels/                    ← One file per source, each subclasses Channel
│   │   ├── base.py                  ← Abstract Channel: can_handle(), read(), search(), check()
│   │   ├── web.py                   ← General web (Jina Reader / Crawl4AI / Rust parser)
│   │   ├── arxiv.py                 ← arXiv papers (arxiv library)
│   │   ├── github.py                ← GitHub repos/issues/code (gh CLI + REST API)
│   │   ├── semantic_scholar.py      ← Semantic Scholar (REST API)
│   │   ├── pubmed.py                ← PubMed/NCBI (Biopython Entrez)
│   │   ├── openalex.py              ← OpenAlex (REST API)
│   │   ├── crossref.py              ← Crossref DOI metadata (REST API)
│   │   ├── europe_pmc.py            ← Europe PMC full-text (REST API)
│   │   ├── youtube.py               ← YouTube transcripts (youtube-transcript-api / yt-dlp)
│   │   ├── rss.py                   ← RSS/Atom feeds (feedparser)
│   │   ├── hacker_news.py           ← Hacker News (Algolia + Firebase API)
│   │   ├── stack_overflow.py        ← Stack Overflow (Stack Exchange API)
│   │   ├── devto.py                 ← DEV.to articles (Forem API)
│   │   ├── wikipedia.py             ← Wikipedia (REST API)
│   │   └── doi_resolver.py          ← DOI → full text resolver (multi-source fallback)
│   ├── formatters/                  ← Output formatting
│   │   ├── markdown.py              ← Clean markdown output
│   │   ├── json_fmt.py              ← Structured JSON output
│   │   └── summary.py               ← LLM-powered summarization
│   ├── integrations/
│   │   └── mcp_server.py            ← MCP server (FastMCP)
│   └── skill/
│       ├── SKILL.md                 ← Agent skill file
│       └── references/              ← Reference docs for agents
├── tests/
│   ├── test_channels.py             ← Per-channel unit tests
│   ├── test_channel_contracts.py    ← Contract tests (all channels implement interface)
│   ├── test_config.py               ← Config read/write/security tests
│   ├── test_cli.py                  ← CLI integration tests
│   ├── test_llm.py                  ← LLM provider adapter tests
│   └── test_doctor.py               ← Doctor report tests
├── docs/
│   ├── research/                    ← Research findings (existing)
│   └── guides/                      ← Setup guides per channel
└── CLAUDE.md                        ← Developer conventions
```

---

## Proposed Changes

### Component 1: Rust Performance Core

The Rust crate provides two high-performance modules exposed to Python via PyO3:

#### [NEW] [Cargo.toml](file:///c:/Users/hp/Downloads/social_dive/Cargo.toml)
Rust workspace root. Dependencies: `pyo3`, `reqwest` (async HTTP), `scraper` (HTML parsing), `rayon` (parallelism), `tokio` (async runtime).

#### [NEW] [src/lib.rs](file:///c:/Users/hp/Downloads/social_dive/src/lib.rs)
Two exported functions:
- `html_to_markdown(html: &str) -> String` — High-speed HTML→clean Markdown conversion using `scraper`. 10-50x faster than Python equivalents for large pages.
- `parallel_fetch(urls: Vec<String>, timeout_ms: u64, max_concurrent: usize) -> Vec<FetchResult>` — Concurrent HTTP fetcher using `reqwest` + `tokio`. Releases the GIL via `py.allow_threads()` so Python continues while Rust fetches.

---

### Component 2: Python Package Foundation

#### [NEW] [pyproject.toml](file:///c:/Users/hp/Downloads/social_dive/pyproject.toml)
Build system: `maturin`. Python ≥3.10. Dependencies: `pyyaml`, `rich`, `loguru`, `httpx`, `openai`, `arxiv`, `feedparser`, `biopython`, `youtube-transcript-api`, `mcp[cli]`. Version: `0.1.0`.

#### [NEW] [social_dive/__init__.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/__init__.py)
Version string (`__version__ = "0.1.0"`), public API surface.

#### [NEW] [social_dive/config.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/config.py)
- Reads/writes `~/.social-dive/config.yaml`
- File created with restrictive permissions (`0o600`) from the start — `os.open()` with `O_CREAT|O_TRUNC` + mode, not open-then-chmod
- Config keys: `nvidia_api_key`, `openai_api_key`, `anthropic_api_key`, `llm_provider` (nvidia|openai|anthropic), `llm_model`, `github_token`, `ncbi_api_key`, `openalex_email`, `cache_dir`, per-channel overrides
- Environment variable fallback: `SOCIAL_DIVE_NVIDIA_API_KEY`, `SOCIAL_DIVE_LLM_PROVIDER`, etc.
- Windows handling: `os.chmod` fallback for NTFS (document that Windows file permissions are limited)

#### [NEW] [social_dive/probe.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/probe.py)
Real-execution prober — not `shutil.which()`. Actually runs the candidate command with a timeout (e.g., `gh --version`, `yt-dlp --version`) and inspects output. Returns structured `ProbeResult(ok: bool, version: str, error: str)`.

#### [NEW] [social_dive/doctor.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/doctor.py)
- Loops all registered channels, calls `channel.check(config)`, catches exceptions per-channel
- Groups results by tier: `zero-config` / `needs-key` / `needs-login` / `error`
- Outputs as rich table (CLI) or JSON (`--json`)
- Never lets a broken channel take down the whole report

#### [NEW] [social_dive/core.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/core.py)
`SocialDive` orchestrator class:
- `read(url: str) -> Content` — dispatches to the right channel via `can_handle()`
- `search(query: str, channels: list[str] | None) -> list[SearchResult]` — fan-out search across selected channels
- `doctor() -> DoctorReport` — delegates to `doctor.py`
- `summarize(content: Content, prompt: str) -> str` — LLM-powered summarization via the configured provider

---

### Component 3: LLM Backend Layer

#### [NEW] [social_dive/llm/base.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/llm/base.py)
```python
class LLMProvider(ABC):
    @abstractmethod
    def complete(self, messages: list[dict], **kwargs) -> CompletionResult: ...
    @abstractmethod
    def available_models(self) -> list[str]: ...
```

#### [NEW] [social_dive/llm/nvidia.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/llm/nvidia.py)
Uses `openai.OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=...)`. Supports:
- GLM-5.x (`glm-5.1`, `glm-5.2` via Zhipu on NVIDIA)
- MiniMax-M3 (`minimax/minimax-m3`)
- DeepSeek-V4 (`deepseek-ai/deepseek-v4-flash`)
- Mistral Medium 3.5 (`mistralai/mistral-medium-3.5-128b`)
- Any other model on NVIDIA NIM — user just sets the model string

#### [NEW] [social_dive/llm/openai_provider.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/llm/openai_provider.py)
Standard OpenAI SDK, `base_url="https://api.openai.com/v1"`. Drop-in for GPT-4o, o3, etc.

#### [NEW] [social_dive/llm/anthropic_provider.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/llm/anthropic_provider.py)
Uses the `anthropic` SDK for Claude models. Adapts the message format as needed.

---

### Component 4: Channels (16 Sources)

Each channel implements the `Channel` abstract base class:

```python
class Channel(ABC):
    name: str               # e.g., "arxiv"
    tier: str               # "zero-config" | "needs-key" | "needs-tool"
    backends: list[str]     # ordered fallback list

    @abstractmethod
    def can_handle(self, url: str) -> bool: ...
    @abstractmethod
    def read(self, url: str, config: Config) -> Content: ...
    @abstractmethod
    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]: ...
    @abstractmethod
    def check(self, config: Config) -> ChannelStatus: ...
```

#### Tier 1 — Zero-Config (no API key needed)

| Channel | File | Backend(s) | Access Method |
|---------|------|-----------|---------------|
| **Web** | `web.py` | Jina Reader → Crawl4AI → Rust parser | `https://r.jina.ai/{url}` (free, no key) |
| **arXiv** | `arxiv.py` | `arxiv` Python lib | arXiv API (free, no key) |
| **RSS** | `rss.py` | `feedparser` | Direct feed parsing (free) |
| **Hacker News** | `hacker_news.py` | Algolia API → Firebase API | REST (free, no key) |
| **Wikipedia** | `wikipedia.py` | REST API | `en.wikipedia.org/api/rest_v1/` (free) |
| **YouTube** | `youtube.py` | `youtube-transcript-api` → `yt-dlp` | Direct transcript extraction (free) |
| **DEV.to** | `devto.py` | Forem API | REST (free, no key for public articles) |
| **Crossref** | `crossref.py` | REST API | `api.crossref.org` (free, polite pool) |
| **DOI Resolver** | `doi_resolver.py` | Crossref → Europe PMC → Unpaywall | Multi-source DOI→full-text chain |

#### Tier 2 — Needs Free Key/Config

| Channel | File | Backend(s) | Key/Config Needed |
|---------|------|-----------|-------------------|
| **GitHub** | `github.py` | `gh` CLI → REST API | GitHub personal access token |
| **Semantic Scholar** | `semantic_scholar.py` | REST API | Optional API key (higher rate limits) |
| **PubMed** | `pubmed.py` | Biopython `Entrez` | NCBI API key (free, 10 req/sec) |
| **OpenAlex** | `openalex.py` | REST API | Free API key (daily quota) |
| **Europe PMC** | `europe_pmc.py` | REST API | None (but email recommended) |
| **Stack Overflow** | `stack_overflow.py` | Stack Exchange API | Optional app key (higher quota) |

#### Tier 3 — Needs External Tool

| Channel | File | Backend(s) | Tool Needed |
|---------|------|-----------|-------------|
| **YouTube (full video)** | `youtube.py` | `yt-dlp` | `yt-dlp` installed |

---

### Component 5: CLI

#### [NEW] [social_dive/cli.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/cli.py)

Commands:
| Command | Description |
|---------|-------------|
| `social-dive read <url>` | Read content from any supported URL |
| `social-dive search <query> [--channels=arxiv,github,...]` | Search across channels |
| `social-dive doctor [--json]` | Health check all channels |
| `social-dive configure <key> <value>` | Set config values |
| `social-dive install [--channels=...] [--safe] [--dry-run]` | Install dependencies |
| `social-dive uninstall [--keep-config]` | Clean up |
| `social-dive summarize <url> [--prompt="..."]` | LLM-powered content summary |
| `social-dive skill --install \| --uninstall` | Manage agent skill files |
| `social-dive version` | Show version |

All commands use `rich` for formatted terminal output. `--json` flag on all commands for machine-readable output.

---

### Component 6: MCP Server Integration

#### [NEW] [social_dive/integrations/mcp_server.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/integrations/mcp_server.py)

Uses `FastMCP` to expose Social Dive as an MCP server:
```python
@mcp.tool()
def read_url(url: str) -> str:
    """Read and extract content from any supported URL."""

@mcp.tool()
def search_sources(query: str, channels: str = "all") -> str:
    """Search across academic, code, and web sources."""

@mcp.tool()
def check_health() -> str:
    """Report which channels are available."""
```

---

### Component 7: Output Formatters

#### [NEW] [social_dive/formatters/markdown.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/formatters/markdown.py)
Clean markdown output with metadata headers (title, author, date, source URL).

#### [NEW] [social_dive/formatters/json_fmt.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/formatters/json_fmt.py)
Structured JSON with `{title, authors, abstract, content, url, source_channel, fetched_at}`.

#### [NEW] [social_dive/formatters/summary.py](file:///c:/Users/hp/Downloads/social_dive/social_dive/formatters/summary.py)
LLM-powered summarization: takes `Content` + optional user prompt, calls configured LLM provider, returns summary.

---

### Component 8: Agent Skill

#### [NEW] [social_dive/skill/SKILL.md](file:///c:/Users/hp/Downloads/social_dive/social_dive/skill/SKILL.md)
The skill document installed into agent skill directories. Tells the agent:
1. Run `social-dive doctor --json` to discover available channels
2. Use `social-dive read <url>` for URL-based content
3. Use `social-dive search <query> --channels=<list>` for research
4. Use `social-dive summarize <url>` for LLM-powered summaries

---

### Component 9: Tests

#### [NEW] [tests/test_channel_contracts.py](file:///c:/Users/hp/Downloads/social_dive/tests/test_channel_contracts.py)
Reflection-based test: discovers all Channel subclasses, asserts each implements `can_handle`, `read`, `search`, `check`. Ensures no channel can be added without the full interface.

#### [NEW] [tests/test_channels.py](file:///c:/Users/hp/Downloads/social_dive/tests/test_channels.py)
Per-channel tests with mock responses. Tests URL pattern matching, result parsing, error handling.

#### [NEW] [tests/test_config.py](file:///c:/Users/hp/Downloads/social_dive/tests/test_config.py)
Config file creation, permission checks, env-var override, key validation.

#### [NEW] [tests/test_cli.py](file:///c:/Users/hp/Downloads/social_dive/tests/test_cli.py)
CLI integration: version sync, help output, `--dry-run` safety.

#### [NEW] [tests/test_llm.py](file:///c:/Users/hp/Downloads/social_dive/tests/test_llm.py)
LLM provider adapter tests: mock API responses, provider switching, error handling.

---

### Component 10: Documentation & Dev Config

#### [MODIFY] [README.md](file:///c:/Users/hp/Downloads/social_dive/README.md)
Full project README with badges, feature matrix, installation instructions, quick-start guide, channel reference table.

#### [NEW] [CLAUDE.md](file:///c:/Users/hp/Downloads/social_dive/CLAUDE.md)
Developer conventions: Python 3.10+, type hints everywhere, `loguru` for logs, `rich` for CLI, version sync rules, testing requirements, branch workflow.

---

## Build Order (Phased)

### Phase 1: Foundation (files 1-10)
1. `pyproject.toml` + `Cargo.toml` + `src/lib.rs` (Rust skeleton)
2. `social_dive/__init__.py` + `config.py`
3. `channels/base.py` + `probe.py` + `doctor.py`
4. `cli.py` (skeleton with `version`, `doctor`, `configure`)
5. `llm/base.py` + `llm/nvidia.py` (primary backend)

### Phase 2: Zero-Config Channels (files 11-19)
6. `channels/web.py` (Jina Reader)
7. `channels/arxiv.py`
8. `channels/rss.py`
9. `channels/youtube.py`
10. `channels/hacker_news.py`
11. `channels/wikipedia.py`
12. `channels/devto.py`
13. `channels/crossref.py`
14. `channels/doi_resolver.py`

### Phase 3: Keyed Channels + LLM Providers (files 20-27)
15. `channels/github.py`
16. `channels/semantic_scholar.py`
17. `channels/pubmed.py`
18. `channels/openalex.py`
19. `channels/europe_pmc.py`
20. `channels/stack_overflow.py`
21. `llm/openai_provider.py`
22. `llm/anthropic_provider.py`

### Phase 4: Integration & Polish (files 28-35)
23. `formatters/` (markdown, json, summary)
24. `integrations/mcp_server.py`
25. `skill/SKILL.md` + references
26. `core.py` (full orchestrator)
27. Complete test suite
28. Full `README.md` + `CLAUDE.md`

---

## Key Differentiators vs. Agent Reach

| Aspect | Agent Reach | Social Dive |
|--------|------------|-------------|
| **Focus** | Social media + general web (15 platforms) | Knowledge sources: papers, code, articles (16+ sources) |
| **ToS Risk** | High (cookie/session scraping for Twitter, Reddit, etc.) | Low (API-blessed sources only) |
| **Language** | Pure Python | Python + Rust (hot-path performance) |
| **LLM Integration** | None (pure routing) | Built-in summarization via pluggable LLM backends |
| **LLM Backends** | N/A | NVIDIA NIM (GLM, MiniMax, DeepSeek), OpenAI, Anthropic |
| **MCP** | Basic server | Full FastMCP integration from day 1 |
| **Content Types** | Raw content only | Raw + structured JSON + LLM summaries |

---

## Verification Plan

### Automated Tests
```bash
# Run full test suite
pytest tests/ -v

# Run contract tests (ensures all channels implement interface)
pytest tests/test_channel_contracts.py -v

# Run with coverage
pytest tests/ --cov=social_dive --cov-report=term-missing

# Type checking
mypy social_dive/
```

### Manual Verification
- `social-dive doctor` produces a complete, formatted status report
- `social-dive read https://arxiv.org/abs/2401.12345` returns paper content
- `social-dive search "transformer architecture" --channels=arxiv,semantic_scholar` returns results
- `social-dive configure nvidia_api_key <key>` writes securely
- Rust module imports successfully: `python -c "from _social_dive_core import html_to_markdown"`
- MCP server starts and responds to tool calls

### Build Verification
```bash
# Build Rust extension
maturin develop

# Verify package installs
pip install -e .

# Verify CLI entry point
social-dive version
```
