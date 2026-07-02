"""
Web channel — general web page reader.

Backends (ordered fallback):
  1. Jina Reader API (https://r.jina.ai/) — free, no key, returns Markdown
  2. Rust html_to_markdown — local, fast, uses the Rust core module
  3. httpx + basic HTML stripping — pure Python fallback
"""

from __future__ import annotations

import re

import httpx
from loguru import logger

from social_dive.channels import (
    Channel,
    ChannelStatus,
    ChannelTier,
    Content,
    SearchResult,
    StatusLevel,
)
from social_dive.config import Config
from social_dive.doctor import register_channel
from social_dive.probe import probe_url


@register_channel
class WebChannel(Channel):
    name = "web"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["jina-reader", "rust-parser", "httpx-fallback"]

    def can_handle(self, url: str) -> bool:
        """Web channel is the catch-all — handles any HTTP(S) URL."""
        return bool(re.match(r"https?://", url, re.IGNORECASE))

    def read(self, url: str, config: Config) -> Content:
        """Read a web page and return clean Markdown content."""
        # Try backends in order
        for backend in self.backends:
            try:
                if backend == "jina-reader":
                    return self._read_jina(url)
                elif backend == "rust-parser":
                    return self._read_rust(url)
                elif backend == "httpx-fallback":
                    return self._read_httpx(url)
            except Exception as e:
                logger.debug(f"Web backend '{backend}' failed for {url}: {e}")
                continue

        raise RuntimeError(f"All web backends failed for {url}")

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Web channel doesn't support search — use Exa or other search channels."""
        return []

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("jina-reader", "https://r.jina.ai/https://example.com", timeout=15.0)
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="jina-reader",
                message="Jina Reader API reachable",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.WARN,
            tier=self.tier,
            active_backend="httpx-fallback",
            message="Jina Reader unreachable, using httpx fallback",
        )

    # -- Backend implementations --

    def _read_jina(self, url: str) -> Content:
        """Use Jina Reader API to convert web page to Markdown."""
        jina_url = f"https://r.jina.ai/{url}"
        resp = httpx.get(
            jina_url,
            timeout=30.0,
            headers={"Accept": "text/markdown"},
            follow_redirects=True,
        )
        resp.raise_for_status()

        body = resp.text
        # Try to extract title from the first markdown heading
        title = ""
        for line in body.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        return Content(
            title=title,
            body=body,
            url=url,
            source_channel=self.name,
        )

    def _read_rust(self, url: str) -> Content:
        """Fetch HTML with httpx, convert to Markdown using Rust core."""
        from social_dive._core import html_to_markdown

        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()

        markdown = html_to_markdown(resp.text)

        title = ""
        for line in markdown.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break

        return Content(
            title=title,
            body=markdown,
            url=url,
            source_channel=self.name,
        )

    def _read_httpx(self, url: str) -> Content:
        """Pure Python fallback: fetch HTML, do basic tag stripping."""
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()

        html = resp.text
        # Very basic HTML → text
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # Try to get title from <title> tag
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        return Content(
            title=title,
            body=text,
            url=url,
            source_channel=self.name,
        )
