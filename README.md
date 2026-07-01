# Social Dive

A from-scratch, improved successor to [Agent Reach](https://github.com/Panniantong/Agent-Reach) — an
AI-agent internet-access capability layer (installer + doctor + config tool for 15+ platforms).

## Goals vs. the original

- **Hybrid Python + Rust**: orchestration/CLI/config in Python, performance/reliability-critical
  parsing/networking/scraping in Rust (via PyO3/maturin or a standalone Rust binary).
- **Pluggable LLM backend layer**: primary development backend is NVIDIA-hosted GLM-5.1 and
  MiniMax (via an NVIDIA API key), but the interface must also be drop-in compatible with the
  OpenAI API shape and the Anthropic API shape, so users can swap providers without touching
  application code.
- Keep the original's core insight: it's a glue/routing layer, not a wrapper — agents call
  upstream tools directly after setup.

## Status

Research phase. See `docs/research/` for findings (organized by source type: web, arxiv, github,
publications) and `docs/plans/` for the resulting architecture/build plan once research lands.

## Constraints carried over from studying the original repo

- Platform ToS risk is real for cookie/session-based scraping (Twitter, Reddit, Instagram, XHS) —
  ban risk falls on the end user, not just the tool author.
- Third-party CLI dependencies (twitter-cli, rdt-cli, bili-cli, OpenCLI) are external projects
  outside our control — they can break, go unmaintained, or disappear.
- This category of tool requires ongoing maintenance (upstream access methods change constantly),
  not just an initial build.
