"""
Channel base-class helper tests — ordered_backends() override behavior and
the two-pass select_backend() selection logic.
"""

from __future__ import annotations

from social_dive.channels import (
    Channel,
    ChannelStatus,
    ChannelTier,
    Content,
    SearchResult,
    StatusLevel,
)
from social_dive.config import Config


class _MultiBackendChannel(Channel):
    name = "multi"
    tier = ChannelTier.ZERO_CONFIG
    backends = ["alpha", "beta", "gamma"]

    def can_handle(self, url: str) -> bool:
        return True

    def read(self, url: str, config: Config) -> Content:
        return Content()

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        return []

    def check(self, config: Config) -> ChannelStatus:
        return ChannelStatus(channel=self.name, level=StatusLevel.OK, tier=self.tier)


class TestOrderedBackends:
    def test_default_order_without_config(self):
        ch = _MultiBackendChannel()
        assert ch.ordered_backends() == ["alpha", "beta", "gamma"]

    def test_default_order_with_empty_config(self, tmp_path):
        ch = _MultiBackendChannel()
        cfg = Config(config_dir=tmp_path / ".sd")
        assert ch.ordered_backends(cfg) == ["alpha", "beta", "gamma"]

    def test_override_moves_backend_to_front(self, tmp_path):
        ch = _MultiBackendChannel()
        cfg = Config(config_dir=tmp_path / ".sd")
        cfg.set("multi_backend", "gamma")
        assert ch.ordered_backends(cfg) == ["gamma", "alpha", "beta"]

    def test_unknown_override_is_ignored(self, tmp_path):
        ch = _MultiBackendChannel()
        cfg = Config(config_dir=tmp_path / ".sd")
        cfg.set("multi_backend", "does-not-exist")
        assert ch.ordered_backends(cfg) == ["alpha", "beta", "gamma"]

    def test_env_var_override(self, tmp_path, monkeypatch):
        ch = _MultiBackendChannel()
        cfg = Config(config_dir=tmp_path / ".sd")
        monkeypatch.setenv("SOCIAL_DIVE_MULTI_BACKEND", "beta")
        assert ch.ordered_backends(cfg) == ["beta", "alpha", "gamma"]

    def test_backend_override_key_does_not_warn(self, tmp_path, caplog):
        """The <channel>_backend key family is valid without CONFIG_KEYS membership."""
        cfg = Config(config_dir=tmp_path / ".sd")
        cfg.set("multi_backend", "beta")  # must not log an "unknown config key" warning
        assert "unknown config key" not in caplog.text.lower()


class TestSelectBackend:
    def test_prefers_ok_over_warn(self):
        ch = _MultiBackendChannel()
        chosen = ch.select_backend([
            ("alpha", StatusLevel.WARN, "degraded"),
            ("beta", StatusLevel.OK, "working"),
        ])
        assert chosen == ("beta", StatusLevel.OK, "working")

    def test_falls_back_to_warn_when_no_ok(self):
        ch = _MultiBackendChannel()
        chosen = ch.select_backend([
            ("alpha", StatusLevel.ERROR, "broken"),
            ("beta", StatusLevel.WARN, "needs auth"),
        ])
        assert chosen == ("beta", StatusLevel.WARN, "needs auth")

    def test_falls_back_to_first_when_only_errors(self):
        ch = _MultiBackendChannel()
        chosen = ch.select_backend([
            ("alpha", StatusLevel.ERROR, "broken"),
            ("beta", StatusLevel.ERROR, "also broken"),
        ])
        assert chosen == ("alpha", StatusLevel.ERROR, "broken")

    def test_empty_returns_none(self):
        ch = _MultiBackendChannel()
        assert ch.select_backend([]) is None

    def test_first_ok_wins_when_multiple_ok(self):
        ch = _MultiBackendChannel()
        chosen = ch.select_backend([
            ("alpha", StatusLevel.OK, "first"),
            ("beta", StatusLevel.OK, "second"),
        ])
        assert chosen == ("alpha", StatusLevel.OK, "first")
