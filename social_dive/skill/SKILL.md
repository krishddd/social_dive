---
name: social-dive
description: >
  Read and search 15+ research/dev/web sources (arXiv, GitHub, PubMed,
  Semantic Scholar, YouTube, Wikipedia, Hacker News, Stack Overflow, DEV.to,
  RSS feeds, Crossref, OpenAlex, Europe PMC, DOI resolver, and any web page).
  USE THIS whenever the user wants to research a topic, read a paper / repo /
  article / video transcript, resolve a DOI, or search academic and developer
  sources. Every result carries a verbatim source URL for citation. Includes
  LLM-powered summarization via NVIDIA NIM, OpenAI, or Anthropic.
triggers:
  research: research, look up, find papers on, what does the literature say, survey
  read: read this, summarize this url, open this paper/repo/article/video
  search: search arxiv/github/stackoverflow/wikipedia for, find the repo/paper for
---

# Social Dive Skill

## When to use this skill

Use Social Dive when the user asks you to:
- Research a topic across academic papers, code, or web sources
- Read content from a URL (paper, repo, article, video transcript, etc.)
- Search for papers, code, articles, or Q&A on a topic
- Read social/platform content (Twitter/X, Reddit, Bilibili, Xiaohongshu,
  Instagram, LinkedIn, Facebook, Xueqiu, Xiaoyuzhou, V2EX)
- Summarize content from any supported source
- Check which knowledge sources are currently available

Social channels are login-gated: `doctor` shows whether a backend (OpenCLI or a
platform CLI/cookies) is set up. If a social read returns `error_code:
unauthenticated`, tell the user to run `social-dive doctor` and
`social-dive configure --from-browser chrome` — and to use a throwaway account.

## How to use

### Step 1: Check available channels (always first)

```bash
social-dive doctor --json
```

Returns each channel's `status` (ok/warn/off/error), its `active_backend`, and a
`message`. Prefer `ok` channels; a `warn` channel usually still works but is
degraded (e.g. missing API key). Backends change availability, so check first.

### Step 2: Read one or more URLs

```bash
social-dive read <url> --format=json
social-dive read <url1> <url2> <url3>          # fetched concurrently
social-dive read <url> --summarize
```

- A single URL is dispatched to the best channel for it and returns one JSON
  object; multiple URLs return a JSON array (fetched in parallel).
- Results include `url`, `title`, `backend`, and `fetched_at`. On failure you get
  a structured `error_code` (`rate_limited`, `unauthenticated`, `restricted`,
  `timeout`, `not_found`, `error`) instead of a crash — check it before using.

### Step 3: Search across sources

```bash
social-dive search "transformer architecture" --channels=arxiv,semantic_scholar --limit=10 --format=json
social-dive search "Python async patterns" --channels=github,stack_overflow,devto
social-dive search "CRISPR gene therapy" --channels=pubmed,openalex,europe_pmc
```

The JSON response has `results` (each with a verbatim URL) and `skipped` — a map
of channel → why it returned nothing (`not_supported`, `rate_limited`, …). If
`results` is empty but you expected hits, `skipped` tells you whether
reformulating the query is worth it.

### Step 4: Summarize content

```bash
social-dive summarize <url>
social-dive summarize <url> --prompt="Focus on the methodology"
```

## Citations

Never invent URLs. Every `url` field is returned verbatim from the upstream
API — cite those exactly.

## Channel Reference

| Channel | What it searches | URL patterns |
|---------|-----------------|--------------|
| arxiv | Academic preprints | arxiv.org/abs/, arxiv.org/pdf/ |
| github | Repositories, issues, PRs | github.com/ |
| semantic_scholar | Academic papers + citations | semanticscholar.org/ |
| pubmed | Biomedical literature | pubmed.ncbi.nlm.nih.gov/ |
| openalex | Scholarly works (200M+) | openalex.org/ |
| europe_pmc | Open-access biomedical papers | europepmc.org/ |
| crossref | DOI metadata + citations | doi.org/ |
| youtube | Video transcripts | youtube.com/, youtu.be/ |
| wikipedia | Encyclopedia articles | wikipedia.org/wiki/ |
| hacker_news | Tech news + discussions | news.ycombinator.com/ |
| stack_overflow | Programming Q&A | stackoverflow.com/ |
| devto | Developer articles | dev.to/ |
| rss | RSS/Atom feeds | */rss, */feed, *.xml |
| web | Any web page | https://* |
| doi_resolver | DOI → full text | Raw DOI strings |
