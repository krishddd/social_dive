# Changelog

All notable changes to Social Dive are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [0.2.0]

A research-grounded reliability and infrastructure upgrade across five phases.

### Added
- **Structured result schema** — `Content`/`SearchResult` now carry a `backend`
  (which backend served the result) and a centrally-stamped `fetched_at`.
  `search()` returns a `SearchResponse(results, skipped)` where `skipped`
  explains *why* a channel contributed nothing (`not_supported`, `rate_limited`,
  …), so an agent can distinguish "found nothing" from "couldn't search".
- **Per-channel backend override** — `Channel.ordered_backends()` honours a
  `<channel>_backend` config key / `SOCIAL_DIVE_<CHANNEL>_BACKEND` env var, plus
  a shared two-pass `select_backend()` helper (OK → WARN → rest).
- **Shared HTTP client** (`social_dive/http_client.py`) — one `httpx` client
  with per-host token-bucket rate limiting and a `diskcache` on-disk response
  cache that honours `Retry-After` / `X-RateLimit-*` and `ETag`/`If-Modified-Since`
  revalidation. Finally uses the previously-unused `cache_dir` config key.
- **Good-citizen web reading** — the web channel prefers a site's `/llms.txt`
  over crude tag-stripping, and respects Cloudflare's Content-Signal
  `ai-input=no` opt-out (overridable via `web_ignore_ai_signals`).
- **`read_many` / multi-URL read** — `social-dive read <url1> <url2> …` fetches
  concurrently via the Rust `parallel_fetch` core (previously dead code), with a
  sequential fallback when the Rust extension isn't built.
- **Real `install` / `uninstall` / `skill` commands** — previously stubbed.
  `install` detects missing per-channel deps against a fixed pinned allow-list
  and supports `--dry-run` / `--safe`; `skill` installs `SKILL.md` into agent
  homes with Windows-safe replacement.

### Changed
- **MCP server** rewritten on `@mcp.tool()` with `readOnlyHint`/`openWorldHint`
  annotations. `search_sources` is renamed to **`search`**; the old name remains
  as a **deprecated alias** (logs a warning) for one release — update MCP client
  configs accordingly. New `read_many` tool added.
- **OpenAlex** `openalex_api_key` is now **soft-required**: a missing key is a
  loud `warn` (degraded), not a hard failure, reflecting OpenAlex retiring its
  free polite pool in Feb 2026.
- Channel `read()`/`search()` failures now degrade to structured `error_code`s
  instead of propagating exceptions.

### Fixed
- Rust `Element::attr()` used a non-existent `scraper::node::Qual` struct, which
  broke every CI build; corrected to a plain `&str`.
- Cached responses dropped `Content-Encoding`/`Content-Length` headers so a
  gzipped entry no longer triggers a double-decode `DecodingError` on cache hit.

## [0.1.0]

Initial release — channel plugin architecture, doctor/probe health checks,
secure config store, 15 research/dev/web channels, and a Rust HTML→Markdown core.
