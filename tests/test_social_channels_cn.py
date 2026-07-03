"""
Tests for the Chinese + misc social channels and the two API channels
(v2ex, exa_search). Network/CLIs are mocked.
"""

from __future__ import annotations

import httpx
import pytest

from social_dive.channels import SearchNotSupportedError
from social_dive.channels.bilibili import BilibiliChannel
from social_dive.channels.exa_search import ExaSearchChannel
from social_dive.channels.v2ex import V2EXChannel
from social_dive.channels.xiaohongshu import XiaohongshuChannel
from social_dive.channels.xiaoyuzhou import XiaoyuzhouChannel
from social_dive.channels.xueqiu import XueqiuChannel
from social_dive.config import Config


@pytest.fixture
def cfg(tmp_path):
    return Config(config_dir=tmp_path / ".sd")


class TestUrlMatching:
    def test_bilibili(self):
        ch = BilibiliChannel()
        assert ch.can_handle("https://www.bilibili.com/video/BV1")
        assert ch.can_handle("https://b23.tv/abc")

    def test_xiaohongshu(self):
        ch = XiaohongshuChannel()
        assert ch.can_handle("https://www.xiaohongshu.com/explore/1")
        assert ch.can_handle("https://xhslink.com/abc")

    def test_xueqiu_and_xiaoyuzhou(self):
        assert XueqiuChannel().can_handle("https://xueqiu.com/1234/567")
        assert XiaoyuzhouChannel().can_handle("https://www.xiaoyuzhoufm.com/episode/1")

    def test_v2ex(self):
        ch = V2EXChannel()
        assert ch.can_handle("https://www.v2ex.com/t/123456")
        assert V2EXChannel._extract_id("https://www.v2ex.com/t/123456#reply1") == "123456"


class TestSearchCapability:
    def test_bilibili_and_xhs_support_search(self):
        assert BilibiliChannel().supports_search is True
        assert XiaohongshuChannel().supports_search is True

    def test_readonly_reject_search(self, cfg):
        for cls in (XueqiuChannel, XiaoyuzhouChannel):
            with pytest.raises(SearchNotSupportedError):
                cls().search("q", cfg)

    def test_v2ex_search_not_supported(self, cfg):
        with pytest.raises(SearchNotSupportedError):
            V2EXChannel().search("q", cfg)


class TestV2EXRead:
    def test_read_parses_topic(self, cfg, monkeypatch):
        payload = [{
            "title": "A topic", "content": "hello", "url": "https://v2ex.com/t/1",
            "member": {"username": "alice"}, "replies": 3, "node": {"name": "tech"},
        }]

        class _Client:
            def get(self, *a, **k):
                return httpx.Response(200, json=payload, request=httpx.Request("GET", "https://v2ex.com"))

        monkeypatch.setattr("social_dive.channels.v2ex.get_client", lambda config=None: _Client())
        content = V2EXChannel().read("https://www.v2ex.com/t/1", cfg)
        assert content.title == "A topic"
        assert content.authors == ["alice"]
        assert content.backend == "v2ex-api"


class TestExaSearch:
    def test_is_search_only(self):
        assert ExaSearchChannel().can_handle("https://anything.com") is False

    def test_search_without_key_raises(self, cfg):
        with pytest.raises(SearchNotSupportedError, match="API key"):
            ExaSearchChannel().search("q", cfg)

    def test_search_parses_results(self, cfg, monkeypatch):
        cfg.set("exa_api_key", "exa-test")
        payload = {"results": [
            {"title": "R1", "url": "https://a", "highlights": ["snip"],
             "author": "bob", "score": 0.9},
        ]}

        def fake_post(*a, **k):
            return httpx.Response(
                200, json=payload, request=httpx.Request("POST", _exa())
            )

        monkeypatch.setattr("social_dive.channels.exa_search.httpx.post", fake_post)
        results = ExaSearchChannel().search("q", cfg, limit=5)
        assert results[0].title == "R1"
        assert results[0].snippet == "snip"
        assert results[0].backend == "exa-api"

    def test_check_warns_without_key(self, cfg):
        assert ExaSearchChannel().check(cfg).level.value == "warn"


def _exa() -> str:
    return "https://api.exa.ai/search"
