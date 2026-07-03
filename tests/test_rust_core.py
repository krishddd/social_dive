"""
Rust core (_social_dive_core) runtime smoke tests.

These exercise the actual compiled Rust functions — not a mock — so CI proves
the extension *runs*, not merely that it *compiles*. They importorskip when the
extension isn't built (e.g. a pure-Python dev checkout), and run for real on CI
where maturin builds it.
"""

from __future__ import annotations

import pytest

core = pytest.importorskip("social_dive._core")


class TestHtmlToMarkdown:
    def test_headings_and_paragraph(self):
        md = core.html_to_markdown("<h1>Title</h1><p>Hello world</p>")
        assert "Title" in md
        assert "Hello world" in md
        assert "#" in md  # heading marker emitted

    def test_links_are_converted(self):
        md = core.html_to_markdown('<a href="https://example.com">click</a>')
        assert "https://example.com" in md
        assert "click" in md

    def test_scripts_are_stripped(self):
        md = core.html_to_markdown("<p>keep</p><script>var secret=1;</script>")
        assert "keep" in md
        assert "secret" not in md

    def test_empty_input(self):
        assert core.html_to_markdown("") == ""


class TestParallelFetch:
    def test_exports_parallel_fetch(self):
        # Presence + basic contract (no network): an empty URL list returns
        # an empty result list without error.
        assert hasattr(core, "parallel_fetch")
        results = core.parallel_fetch([])
        assert list(results) == []
