"""
Core dispatcher tests — structured error degradation, centralized timestamps,
and SearchResponse.skipped population.

Uses fake in-process Channel subclasses (no network) so these tests exercise
only SocialDive's dispatch logic in core.py, not any real backend.
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass

import httpx
import pytest

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
from social_dive.core import SocialDive


class _OkChannel(Channel):
    name = "ok_channel"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["fake-backend"]

    def can_handle(self, url: str) -> bool:
        return True

    def read(self, url: str, config: Config) -> Content:
        return Content(title="fine", url=url, source_channel=self.name, backend=self.backends[0])

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        return [SearchResult(title="hit", url="https://example.com/1", source_channel=self.name)]

    def check(self, config: Config) -> ChannelStatus:
        return ChannelStatus(channel=self.name, level=StatusLevel.OK, tier=self.tier)


class _ValueErrorChannel(Channel):
    name = "value_error_channel"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["fake-backend"]

    def can_handle(self, url: str) -> bool:
        return True

    def read(self, url: str, config: Config) -> Content:
        raise ValueError("could not extract ID")

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        raise ValueError("could not extract ID")

    def check(self, config: Config) -> ChannelStatus:
        return ChannelStatus(channel=self.name, level=StatusLevel.OK, tier=self.tier)


class _RateLimitedChannel(Channel):
    name = "rate_limited_channel"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["fake-backend"]

    def can_handle(self, url: str) -> bool:
        return True

    def read(self, url: str, config: Config) -> Content:
        raise self._make_429()

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        raise self._make_429()

    @staticmethod
    def _make_429() -> httpx.HTTPStatusError:
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(429, request=request)
        return httpx.HTTPStatusError("429", request=request, response=response)

    def check(self, config: Config) -> ChannelStatus:
        return ChannelStatus(channel=self.name, level=StatusLevel.OK, tier=self.tier)


class _ThirdPartyRateLimitChannel(Channel):
    """Simulates a channel wrapping a client (like the `arxiv` package) that
    raises its own exception type for a 429 rather than httpx's."""

    name = "third_party_rate_limit_channel"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["fake-backend"]

    def can_handle(self, url: str) -> bool:
        return True

    def read(self, url: str, config: Config) -> Content:
        raise RuntimeError("Page request resulted in HTTP 429 (https://example.com)")

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        raise RuntimeError("Page request resulted in HTTP 429 (https://example.com)")

    def check(self, config: Config) -> ChannelStatus:
        return ChannelStatus(channel=self.name, level=StatusLevel.OK, tier=self.tier)


class _NoSearchChannel(Channel):
    name = "no_search_channel"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["fake-backend"]

    def can_handle(self, url: str) -> bool:
        return True

    def read(self, url: str, config: Config) -> Content:
        return Content(title="fine", url=url, source_channel=self.name)

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        raise SearchNotSupportedError("no search index for this source")

    def check(self, config: Config) -> ChannelStatus:
        return ChannelStatus(channel=self.name, level=StatusLevel.OK, tier=self.tier)


@pytest.fixture
def sd(tmp_path) -> SocialDive:
    instance = SocialDive(config=Config(config_dir=tmp_path / ".social-dive-test"))
    return instance


class TestReadDispatch:
    def test_channel_exception_degrades_to_structured_content(self, sd):
        sd._channels = [_ValueErrorChannel()]
        content = sd.read("https://example.com/anything")
        assert content.error_code == "not_found"
        assert "could not extract ID" in content.body
        assert content.source_channel == "value_error_channel"

    def test_http_429_classifies_as_rate_limited(self, sd):
        sd._channels = [_RateLimitedChannel()]
        content = sd.read("https://example.com/anything")
        assert content.error_code == "rate_limited"

    def test_no_matching_channel_still_raises(self, sd):
        sd._channels = []
        with pytest.raises(ValueError, match="No channel can handle URL"):
            sd.read("https://example.com/anything")

    def test_fetched_at_stamped_centrally_on_success(self, sd):
        sd._channels = [_OkChannel()]
        content = sd.read("https://example.com/anything")
        assert content.fetched_at  # overwritten by the dispatcher, not just the channel's default

    def test_non_httpx_429_in_message_still_classifies_as_rate_limited(self, sd):
        """Covers a client (like the `arxiv` package) that raises its own
        exception type for an HTTP error rather than httpx's."""
        sd._channels = [_ThirdPartyRateLimitChannel()]
        content = sd.read("https://example.com/anything")
        assert content.error_code == "rate_limited"


class TestSearchDispatch:
    def test_not_supported_channel_recorded_in_skipped(self, sd):
        sd._channels = [_NoSearchChannel()]
        response = sd.search("query")
        assert response.results == []
        assert "no_search_channel" in response.skipped
        assert response.skipped["no_search_channel"].startswith("not_supported:")

    def test_errored_channel_recorded_in_skipped_not_raised(self, sd):
        sd._channels = [_ValueErrorChannel()]
        response = sd.search("query")
        assert response.results == []
        assert response.skipped["value_error_channel"].startswith("not_found:")

    def test_successful_channel_populates_results_and_fetched_at(self, sd):
        sd._channels = [_OkChannel()]
        response = sd.search("query")
        assert len(response.results) == 1
        assert response.results[0].fetched_at
        assert response.skipped == {}

    def test_mixed_channels_partition_correctly(self, sd):
        sd._channels = [_OkChannel(), _NoSearchChannel()]
        response = sd.search("query")
        assert len(response.results) == 1
        assert list(response.skipped.keys()) == ["no_search_channel"]


@dataclass
class _FakeFetch:
    url: str
    status: int
    body: str
    error: str = ""
    ok: bool = True


def _install_fake_core(monkeypatch, results):
    """Install a fake social_dive._core exposing parallel_fetch + html_to_markdown."""
    mod = types.ModuleType("social_dive._core")
    mod.parallel_fetch = lambda urls: results
    mod.html_to_markdown = lambda html: f"# converted\n{html}"
    monkeypatch.setitem(sys.modules, "social_dive._core", mod)


class TestReadMany:
    def test_single_url_uses_normal_read(self, sd):
        # A one-URL read_many must behave exactly like a single read (dispatch),
        # not touch parallel_fetch.
        sd._channels = [_OkChannel()]
        results = sd.read_many(["https://example.com/x"])
        assert len(results) == 1
        assert results[0].title == "fine"

    def test_multiple_urls_use_parallel_fetch(self, sd, monkeypatch):
        _install_fake_core(
            monkeypatch,
            [
                _FakeFetch("https://a.com", 200, "<p>A</p>"),
                _FakeFetch("https://b.com", 200, "<p>B</p>"),
            ],
        )
        results = sd.read_many(["https://a.com", "https://b.com"])
        assert [c.url for c in results] == ["https://a.com", "https://b.com"]
        assert all(c.backend == "parallel-fetch" for c in results)
        assert all(c.body.startswith("# converted") for c in results)
        assert all(c.fetched_at for c in results)

    def test_failed_fetch_becomes_structured_error(self, sd, monkeypatch):
        _install_fake_core(
            monkeypatch,
            [
                _FakeFetch("https://ok.com", 200, "<p>ok</p>"),
                _FakeFetch("https://bad.com", 0, "", error="Request error", ok=False),
                _FakeFetch("https://limited.com", 429, "", error="rate", ok=False),
            ],
        )
        results = sd.read_many(["https://ok.com", "https://bad.com", "https://limited.com"])
        assert results[0].error_code is None
        assert results[1].error_code == "error"
        assert results[2].error_code == "rate_limited"

    def test_sequential_fallback_when_core_missing(self, sd, monkeypatch):
        # Ensure the fake module is absent so the import raises ImportError.
        monkeypatch.setitem(sys.modules, "social_dive._core", None)
        sd._channels = [_OkChannel()]
        results = sd.read_many(["https://a.com", "https://b.com"])
        assert len(results) == 2
        assert all(c.title == "fine" for c in results)  # went through normal read()
