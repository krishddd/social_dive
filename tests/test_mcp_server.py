"""
MCP server tests.

The `mcp` package is a hard dependency but may be absent in a minimal local
env, so the module import is guarded with importorskip — these run in CI
(which installs mcp[cli]).

Tests exercise the import-light `_do_*` helpers with a fake SocialDive so no
network or real channels are involved, and confirm the deprecated `search_sources`
alias forwards to the same logic as `search`.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")

import social_dive.integrations.mcp_server as server  # noqa: E402
from social_dive.channels import Content, SearchResult  # noqa: E402
from social_dive.core import SearchResponse  # noqa: E402


class _FakeSD:
    def read(self, url):
        return Content(title="T", url=url, body="body", source_channel="web", backend="jina-reader")

    def read_many(self, urls):
        return [Content(title=f"T{i}", url=u, source_channel="web") for i, u in enumerate(urls)]

    def search(self, query, channels=None, limit=10):
        return SearchResponse(
            results=[SearchResult(title="hit", url="https://x/1", source_channel="arxiv")],
            skipped={"rss": "not_supported: no index"},
        )


@pytest.fixture
def fake_sd(monkeypatch):
    sd = _FakeSD()
    monkeypatch.setattr(server, "_get_sd", lambda: sd)
    return sd


class TestTools:
    def test_read_url(self, fake_sd):
        out = server._do_read("https://example.com")
        assert "T" in out  # markdown-formatted title

    def test_read_many_returns_json_array(self, fake_sd):
        out = json.loads(server._do_read_many(["https://a", "https://b"]))
        assert isinstance(out, list)
        assert [c["url"] for c in out] == ["https://a", "https://b"]

    def test_search_returns_results_and_skipped(self, fake_sd):
        out = json.loads(server._do_search("q", "arxiv", 5))
        assert out["results"][0]["url"] == "https://x/1"
        assert "rss" in out["skipped"]

    def test_search_all_channels(self, fake_sd):
        out = json.loads(server._do_search("q", "all", 5))
        assert len(out["results"]) == 1


class TestRegistration:
    def test_expected_tools_are_defined(self):
        for name in ["read_url", "read_many", "search", "check_health",
                     "summarize_url", "list_channels"]:
            assert callable(getattr(server, name)), f"missing tool {name}"

    def test_deprecated_alias_forwards_to_search(self, fake_sd):
        # Both the alias and the canonical tool produce identical output.
        assert server.search("q", "all", 3) == server.search_sources("q", "all", 3)
