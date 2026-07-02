"""
Result-schema tests — Content/SearchResult new fields, SearchNotSupportedError.
"""

from __future__ import annotations

import pytest

from social_dive.channels import Content, SearchNotSupportedError, SearchResult


class TestContent:
    def test_defaults(self):
        c = Content()
        assert c.backend == ""
        assert c.error_code is None
        assert c.fetched_at  # auto-stamped by default_factory

    def test_to_dict_includes_new_fields(self):
        c = Content(backend="arxiv-api", error_code="not_found")
        d = c.to_dict()
        assert d["backend"] == "arxiv-api"
        assert d["error_code"] == "not_found"


class TestSearchResult:
    def test_defaults(self):
        r = SearchResult()
        assert r.backend == ""
        assert r.fetched_at == ""  # stamped centrally by core.py, not per-item

    def test_to_dict_includes_new_fields(self):
        r = SearchResult(backend="gh-cli", fetched_at="2026-07-02T00:00:00")
        d = r.to_dict()
        assert d["backend"] == "gh-cli"
        assert d["fetched_at"] == "2026-07-02T00:00:00"


class TestSearchNotSupportedError:
    def test_is_an_exception(self):
        assert issubclass(SearchNotSupportedError, Exception)

    def test_carries_reason_message(self):
        with pytest.raises(SearchNotSupportedError, match="no search index"):
            raise SearchNotSupportedError("no search index")
