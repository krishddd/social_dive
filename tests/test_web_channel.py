"""
Web channel tests — search-not-supported, llms.txt preference, and robots.txt
AI-signal handling. No network: the shared client is replaced with an
HTTPClient wired to an httpx.MockTransport that routes by URL.

Note: rust-parser always fails locally (the Rust _core extension isn't built
in a type-check/test-only env), so reads naturally fall through jina →
rust-parser → llms-txt → httpx-fallback, which is convenient for exercising
the later backends.
"""

from __future__ import annotations

import httpx
import pytest

from social_dive.channels import SearchNotSupportedError
from social_dive.channels.web import WebChannel
from social_dive.config import Config
from social_dive.http_client import HTTPClient


def _install_client(monkeypatch, routes: dict[str, httpx.Response], tmp_path):
    """Point web.get_client at a MockTransport client routing by URL substring."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for needle, response in routes.items():
            if needle in url:
                return response
        return httpx.Response(404)

    client = HTTPClient(
        cache_dir=tmp_path / "c",
        rate_limit=False,
        cache=False,
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr("social_dive.channels.web.get_client", lambda config=None: client)
    return client


@pytest.fixture(autouse=True)
def no_rust_backend(monkeypatch):
    """Exercise the Python backend chain deterministically.

    These tests target the jina / llms-txt / httpx selection and the
    robots/llms logic. Whether the Rust `rust-parser` backend is available
    depends on the build (present in CI, absent in a pure-Python checkout), so
    exclude it here to keep behavior deterministic — the Rust path itself is
    covered by tests/test_rust_core.py.
    """
    monkeypatch.setattr(
        WebChannel, "backends", ["jina-reader", "llms-txt", "httpx-fallback"]
    )


@pytest.fixture
def cfg(tmp_path):
    return Config(config_dir=tmp_path / ".sd")


class TestSearch:
    def test_search_not_supported(self, cfg):
        with pytest.raises(SearchNotSupportedError):
            WebChannel().search("anything", cfg)


class TestLlmsTxt:
    def test_prefers_llms_txt_when_page_readers_fail(self, cfg, tmp_path, monkeypatch):
        _install_client(
            monkeypatch,
            {
                "r.jina.ai": httpx.Response(500),  # jina fails
                "/llms.txt": httpx.Response(200, text="# Example Site\nClean summary."),
            },
            tmp_path,
        )
        content = WebChannel().read("https://example.com/page", cfg)
        assert content.backend == "llms-txt"
        assert content.title == "Example Site"
        assert content.metadata["llms_txt_url"] == "https://example.com/llms.txt"

    def test_empty_llms_txt_falls_through_to_httpx(self, cfg, tmp_path, monkeypatch):
        _install_client(
            monkeypatch,
            {
                "r.jina.ai": httpx.Response(500),
                "/llms.txt": httpx.Response(200, text="   "),  # blank → skip
                "/robots.txt": httpx.Response(404),
                "example.com/page": httpx.Response(200, text="<title>Hi</title><p>Body</p>"),
            },
            tmp_path,
        )
        content = WebChannel().read("https://example.com/page", cfg)
        assert content.backend == "httpx-fallback"
        assert content.title == "Hi"


class TestRobotsAiSignal:
    def test_ai_input_disallowed_blocks_read(self, cfg, tmp_path, monkeypatch):
        _install_client(
            monkeypatch,
            {"/robots.txt": httpx.Response(200, text="Content-Signal: ai-input=no, ai-train=no")},
            tmp_path,
        )
        content = WebChannel().read("https://example.com/page", cfg)
        assert content.error_code == "restricted"
        assert content.metadata["robots_ai_input"] == "disallowed"

    def test_ai_input_override_allows_read(self, cfg, tmp_path, monkeypatch):
        cfg.set("web_ignore_ai_signals", "true")
        _install_client(
            monkeypatch,
            {
                "/robots.txt": httpx.Response(200, text="Content-Signal: ai-input=no"),
                "r.jina.ai": httpx.Response(200, text="# Page\nbody"),
            },
            tmp_path,
        )
        content = WebChannel().read("https://example.com/page", cfg)
        assert content.error_code is None
        assert content.backend == "jina-reader"

    def test_missing_robots_does_not_block(self, cfg, tmp_path, monkeypatch):
        _install_client(
            monkeypatch,
            {
                "/robots.txt": httpx.Response(404),
                "r.jina.ai": httpx.Response(200, text="# Page\nbody"),
            },
            tmp_path,
        )
        content = WebChannel().read("https://example.com/page", cfg)
        assert content.error_code is None
        assert content.backend == "jina-reader"

    def test_classic_disallow_flagged_not_blocked(self, cfg, tmp_path, monkeypatch):
        _install_client(
            monkeypatch,
            {
                "/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /page"),
                "r.jina.ai": httpx.Response(500),
                "/llms.txt": httpx.Response(404),
                "example.com/page": httpx.Response(200, text="<title>T</title>x"),
            },
            tmp_path,
        )
        content = WebChannel().read("https://example.com/page", cfg)
        assert content.error_code is None  # not blocked
        assert content.metadata.get("robots_path_disallowed") is True  # but flagged
