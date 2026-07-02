"""
Web channel — general web page reader (the catch-all).

Backends (ordered fallback, reprioritizable via the ``web_backend`` override):
  1. jina-reader   — Jina Reader API (https://r.jina.ai/), clean Markdown
  2. rust-parser   — local Rust html_to_markdown (fast, offline)
  3. llms-txt      — the site's /llms.txt summary, if it publishes one
  4. httpx-fallback — pure-Python tag stripping (last resort)

Good-citizen behavior: before reading, the channel checks the site's
robots.txt for Cloudflare's Content Signals ``ai-input`` directive and, when a
site has explicitly opted out of AI input, declines to fetch (overridable with
``web_ignore_ai_signals``). Classic ``Disallow`` matches are flagged in
metadata but not blocked — a user-driven reader is not a crawler.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from loguru import logger

from social_dive.channels import (
    Channel,
    ChannelStatus,
    ChannelTier,
    Content,
    SearchNotSupportedError,
    SearchResult,
    StatusLevel,
)
from social_dive.config import Config
from social_dive.doctor import register_channel
from social_dive.http_client import get_client
from social_dive.probe import probe_url


@register_channel
class WebChannel(Channel):
    name = "web"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["jina-reader", "rust-parser", "llms-txt", "httpx-fallback"]

    def can_handle(self, url: str) -> bool:
        """Web channel is the catch-all — handles any HTTP(S) URL."""
        return bool(re.match(r"https?://", url, re.IGNORECASE))

    def read(self, url: str, config: Config) -> Content:
        """Read a web page and return clean Markdown content."""
        # Respect an explicit AI opt-out before making the page request.
        if self._ai_input_disallowed(url, config):
            logger.warning(f"Site opted out of AI input via robots.txt: {url}")
            return Content(
                url=url,
                source_channel=self.name,
                body=f"[Not fetched — {urlparse(url).netloc} opted out of AI input "
                "via its robots.txt Content-Signal. Override with "
                "web_ignore_ai_signals=true.]",
                error_code="restricted",
                metadata={"robots_ai_input": "disallowed"},
            )

        handlers = {
            "jina-reader": self._read_jina,
            "rust-parser": self._read_rust,
            "llms-txt": self._read_llms_txt,
            "httpx-fallback": self._read_httpx,
        }
        for backend in self.ordered_backends(config):
            handler = handlers.get(backend)
            if handler is None:
                continue
            try:
                return handler(url, config)
            except Exception as e:  # noqa: BLE001 — try the next backend
                logger.debug(f"Web backend '{backend}' failed for {url}: {e}")
                continue

        raise RuntimeError(f"All web backends failed for {url}")

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """The web channel is a reader, not a search engine."""
        raise SearchNotSupportedError(
            "The web channel reads a specific URL; use a search-capable channel "
            "(e.g. wikipedia, github) to discover URLs first"
        )

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

    def _read_jina(self, url: str, config: Config) -> Content:
        """Use Jina Reader API to convert web page to Markdown."""
        resp = get_client(config).get(
            f"https://r.jina.ai/{url}",
            timeout=30.0,
            headers={"Accept": "text/markdown"},
        )
        resp.raise_for_status()
        return self._content_from_markdown(url, resp.text, backend="jina-reader")

    def _read_rust(self, url: str, config: Config) -> Content:
        """Fetch HTML with the shared client, convert via the Rust core."""
        from social_dive._core import html_to_markdown

        resp = get_client(config).get(url, timeout=30.0)
        resp.raise_for_status()
        markdown = html_to_markdown(resp.text)
        return self._content_from_markdown(url, markdown, backend="rust-parser")

    def _read_llms_txt(self, url: str, config: Config) -> Content:
        """Prefer a site's /llms.txt summary over crude HTML stripping.

        Cheap and clean when present (nascent standard, ~absent on most sites),
        so this sits ahead of the pure-Python fallback but behind the readers
        that fetch the actual page.
        """
        parsed = urlparse(url)
        llms_url = f"{parsed.scheme}://{parsed.netloc}/llms.txt"
        resp = get_client(config).get(llms_url, timeout=5.0)
        if resp.status_code != 200 or not resp.text.strip():
            raise ValueError("no llms.txt")
        content = self._content_from_markdown(url, resp.text, backend="llms-txt")
        content.metadata["llms_txt_url"] = llms_url
        content.metadata["note"] = "site-level llms.txt summary, not the specific page"
        return content

    def _read_httpx(self, url: str, config: Config) -> Content:
        """Pure Python fallback: fetch HTML, do basic tag stripping."""
        resp = get_client(config).get(url, timeout=30.0)
        resp.raise_for_status()

        html = resp.text
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        content = Content(
            title=title,
            body=text,
            url=url,
            source_channel=self.name,
            backend="httpx-fallback",
        )
        self._flag_classic_disallow(content, url, config)
        return content

    # -- helpers --

    def _content_from_markdown(self, url: str, body: str, *, backend: str) -> Content:
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
            backend=backend,
        )

    def _ai_input_disallowed(self, url: str, config: Config) -> bool:
        """True if the site's robots.txt signals ai-input=no (and not overridden)."""
        if str(config.get("web_ignore_ai_signals", "")).lower() in ("1", "true", "yes"):
            return False
        signals = self._robots_signals(url, config)
        return signals.get("ai_input") == "no"

    def _flag_classic_disallow(self, content: Content, url: str, config: Config) -> None:
        signals = self._robots_signals(url, config)
        if signals.get("path_disallowed"):
            content.metadata["robots_path_disallowed"] = True

    def _robots_signals(self, url: str, config: Config) -> dict[str, object]:
        """Parse robots.txt for the Cloudflare ai-input signal and path rules.

        Best-effort and defensive: any fetch/parse failure yields empty signals
        so a missing or malformed robots.txt never blocks a read.
        """
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            resp = get_client(config).get(robots_url, timeout=5.0)
            if resp.status_code != 200:
                return {}
            text = resp.text
        except Exception:  # noqa: BLE001 — robots is advisory, never fatal
            return {}

        signals: dict[str, object] = {}
        path = parsed.path or "/"
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            lower = line.lower()
            # Cloudflare Content Signals: "Content-Signal: ai-input=no, ai-train=no"
            if lower.startswith("content-signal:"):
                for token in line.split(":", 1)[1].split(","):
                    if "=" in token:
                        key, _, val = token.strip().partition("=")
                        if key.strip().lower() == "ai-input":
                            signals["ai_input"] = val.strip().lower()
            elif lower.startswith("disallow:"):
                rule = line.split(":", 1)[1].strip()
                if rule and path.startswith(rule):
                    signals["path_disallowed"] = True
        return signals
