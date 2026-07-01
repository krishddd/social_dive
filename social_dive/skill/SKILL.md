---
name: social-dive
description: >
  Read and search 16+ internet knowledge sources (arXiv, GitHub, PubMed,
  Semantic Scholar, YouTube, Wikipedia, Hacker News, Stack Overflow, DEV.to,
  RSS feeds, Crossref, OpenAlex, Europe PMC, DOI resolver, and any web page).
  Includes LLM-powered summarization via NVIDIA NIM, OpenAI, or Anthropic.
---

# Social Dive Skill

## When to use this skill

Use Social Dive when the user asks you to:
- Research a topic across academic papers, code, or web sources
- Read content from a URL (paper, repo, article, video transcript, etc.)
- Search for papers, code, articles, or Q&A on a topic
- Summarize content from any supported source
- Check which knowledge sources are currently available

## How to use

### Step 1: Check available channels

```bash
social-dive doctor --json
```

This returns a JSON report showing which channels are working. Use this to
decide which channels to search.

### Step 2: Read a specific URL

```bash
social-dive read <url>
social-dive read <url> --format=json
social-dive read <url> --summarize
```

Supports URLs from: arXiv, GitHub, YouTube, Wikipedia, PubMed, Semantic Scholar,
Hacker News, Stack Overflow, DEV.to, RSS feeds, DOI links, and any web page.

### Step 3: Search across sources

```bash
social-dive search "transformer architecture" --channels=arxiv,semantic_scholar --limit=10
social-dive search "Python async patterns" --channels=github,stack_overflow,devto
social-dive search "CRISPR gene therapy" --channels=pubmed,openalex,europe_pmc
```

### Step 4: Summarize content

```bash
social-dive summarize <url>
social-dive summarize <url> --prompt="Focus on the methodology"
```

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
