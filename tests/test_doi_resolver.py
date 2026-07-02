"""
DOI resolver tests — the read() source chain honours ordered_backends() and
falls through to the next source when one defers (returns None) or raises.

Each source method is monkeypatched so no network is touched.
"""

from __future__ import annotations

import pytest

from social_dive.channels import Content
from social_dive.channels.doi_resolver import DOIResolverChannel
from social_dive.config import Config


@pytest.fixture
def cfg(tmp_path):
    return Config(config_dir=tmp_path / ".sd")


def _content(backend: str) -> Content:
    return Content(title=f"from-{backend}", backend=backend, source_channel="doi_resolver")


def _patch_sources(monkeypatch, europepmc, unpaywall, crossref) -> None:
    """Patch each source method with a callable taking (self, doi, config)."""
    monkeypatch.setattr(DOIResolverChannel, "_try_europepmc", europepmc)
    monkeypatch.setattr(DOIResolverChannel, "_try_unpaywall", unpaywall)
    monkeypatch.setattr(DOIResolverChannel, "_try_crossref", crossref)


def _returns(backend):
    return lambda self, doi, config: _content(backend)


def _defers(self, doi, config):
    return None


def _raises(self, doi, config):
    raise RuntimeError("down")


class TestReadOrder:
    def test_default_order_prefers_europepmc(self, cfg, monkeypatch):
        _patch_sources(
            monkeypatch, _returns("europepmc"), _returns("unpaywall"), _returns("crossref")
        )
        assert DOIResolverChannel().read("10.1/abc", cfg).backend == "europepmc"

    def test_falls_through_when_source_defers(self, cfg, monkeypatch):
        _patch_sources(monkeypatch, _defers, _returns("unpaywall"), _returns("crossref"))
        assert DOIResolverChannel().read("10.1/abc", cfg).backend == "unpaywall"

    def test_falls_through_when_source_raises(self, cfg, monkeypatch):
        _patch_sources(monkeypatch, _raises, _defers, _returns("crossref"))
        assert DOIResolverChannel().read("10.1/abc", cfg).backend == "crossref"

    def test_override_reprioritizes_chain(self, cfg, monkeypatch):
        cfg.set("doi_resolver_backend", "crossref")
        _patch_sources(
            monkeypatch, _returns("europepmc"), _returns("unpaywall"), _returns("crossref")
        )
        # crossref forced to the front, so it wins even though europepmc would too
        assert DOIResolverChannel().read("10.1/abc", cfg).backend == "crossref"

    def test_all_sources_fail_reraises_last_error(self, cfg, monkeypatch):
        _patch_sources(monkeypatch, _raises, _raises, _raises)
        with pytest.raises(RuntimeError, match="down"):
            DOIResolverChannel().read("10.1/abc", cfg)


class TestCheck:
    def test_check_reports_ordered_chain(self, cfg):
        status = DOIResolverChannel().check(cfg)
        assert status.message == "DOI resolver (europepmc → unpaywall → crossref)"

    def test_check_reflects_override(self, cfg):
        cfg.set("doi_resolver_backend", "crossref")
        status = DOIResolverChannel().check(cfg)
        assert status.message.startswith("DOI resolver (crossref →")
