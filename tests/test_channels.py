"""
Unit tests for individual channels — URL pattern matching and data parsing.
"""

from __future__ import annotations

import pytest

from social_dive.channels.arxiv import ArxivChannel
from social_dive.channels.crossref import CrossrefChannel
from social_dive.channels.devto import DevtoChannel
from social_dive.channels.github import GitHubChannel
from social_dive.channels.hacker_news import HackerNewsChannel
from social_dive.channels.rss import RSSChannel
from social_dive.channels.stack_overflow import StackOverflowChannel
from social_dive.channels.web import WebChannel
from social_dive.channels.wikipedia import WikipediaChannel
from social_dive.channels.youtube import YouTubeChannel


class TestArxivChannel:
    def test_can_handle_abs(self):
        ch = ArxivChannel()
        assert ch.can_handle("https://arxiv.org/abs/2401.12345")

    def test_can_handle_pdf(self):
        ch = ArxivChannel()
        assert ch.can_handle("https://arxiv.org/pdf/2401.12345")

    def test_cannot_handle_other(self):
        ch = ArxivChannel()
        assert not ch.can_handle("https://example.com")

    def test_extract_id(self):
        assert ArxivChannel._extract_id("https://arxiv.org/abs/2401.12345") == "2401.12345"
        assert ArxivChannel._extract_id("https://arxiv.org/abs/2401.12345v2") == "2401.12345v2"
        assert ArxivChannel._extract_id("https://arxiv.org/abs/hep-ph/0601001") == "hep-ph/0601001"


class TestYouTubeChannel:
    def test_can_handle_watch(self):
        ch = YouTubeChannel()
        assert ch.can_handle("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_can_handle_short_url(self):
        ch = YouTubeChannel()
        assert ch.can_handle("https://youtu.be/dQw4w9WgXcQ")

    def test_can_handle_shorts(self):
        ch = YouTubeChannel()
        assert ch.can_handle("https://www.youtube.com/shorts/dQw4w9WgXcQ")

    def test_extract_video_id(self):
        assert YouTubeChannel._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert YouTubeChannel._extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


class TestGitHubChannel:
    def test_can_handle_repo(self):
        ch = GitHubChannel()
        assert ch.can_handle("https://github.com/python/cpython")

    def test_can_handle_issue(self):
        ch = GitHubChannel()
        assert ch.can_handle("https://github.com/python/cpython/issues/123")

    def test_parse_repo_url(self):
        result = GitHubChannel._parse_github_url("https://github.com/python/cpython")
        assert result == {"owner": "python", "repo": "cpython"}

    def test_parse_issue_url(self):
        result = GitHubChannel._parse_github_url("https://github.com/python/cpython/issues/123")
        assert result == {"owner": "python", "repo": "cpython", "type": "issues", "number": "123"}


class TestWebChannel:
    def test_can_handle_http(self):
        ch = WebChannel()
        assert ch.can_handle("https://example.com")
        assert ch.can_handle("http://example.com/page")

    def test_cannot_handle_non_http(self):
        ch = WebChannel()
        assert not ch.can_handle("ftp://example.com")


class TestHackerNewsChannel:
    def test_can_handle(self):
        ch = HackerNewsChannel()
        assert ch.can_handle("https://news.ycombinator.com/item?id=12345")

    def test_extract_item_id(self):
        assert HackerNewsChannel._extract_item_id("https://news.ycombinator.com/item?id=12345") == "12345"


class TestWikipediaChannel:
    def test_can_handle(self):
        ch = WikipediaChannel()
        assert ch.can_handle("https://en.wikipedia.org/wiki/Python_(programming_language)")

    def test_extract_title(self):
        title = WikipediaChannel._extract_title("https://en.wikipedia.org/wiki/Python_(programming_language)")
        assert title == "Python (programming language)"


class TestCrossrefChannel:
    def test_can_handle_doi_url(self):
        ch = CrossrefChannel()
        assert ch.can_handle("https://doi.org/10.1038/nature12373")

    def test_extract_doi(self):
        assert CrossrefChannel._extract_doi("https://doi.org/10.1038/nature12373") == "10.1038/nature12373"


class TestRSSChannel:
    def test_can_handle_rss(self):
        ch = RSSChannel()
        assert ch.can_handle("https://example.com/rss")
        assert ch.can_handle("https://example.com/feed.xml")


class TestStackOverflowChannel:
    def test_can_handle(self):
        ch = StackOverflowChannel()
        assert ch.can_handle("https://stackoverflow.com/questions/12345/some-title")

    def test_extract_question_id(self):
        assert StackOverflowChannel._extract_question_id(
            "https://stackoverflow.com/questions/12345/some-title"
        ) == "12345"


class TestDevtoChannel:
    def test_can_handle(self):
        ch = DevtoChannel()
        assert ch.can_handle("https://dev.to/user/article-slug")
