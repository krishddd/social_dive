"""
Social channel tests — URL matching, backend lists, and search capability.
The routing/read/check mechanics are covered in test_social_infra.py; here we
verify each channel's can_handle patterns and search support.
"""

from __future__ import annotations

import pytest

from social_dive.channels import SearchNotSupportedError
from social_dive.channels.facebook import FacebookChannel
from social_dive.channels.instagram import InstagramChannel
from social_dive.channels.linkedin import LinkedInChannel
from social_dive.channels.reddit import RedditChannel
from social_dive.channels.twitter import TwitterChannel
from social_dive.config import Config


@pytest.fixture
def cfg(tmp_path):
    return Config(config_dir=tmp_path / ".sd")


class TestUrlMatching:
    def test_twitter(self):
        ch = TwitterChannel()
        assert ch.can_handle("https://x.com/user/status/123")
        assert ch.can_handle("https://twitter.com/user")
        assert not ch.can_handle("https://reddit.com/r/x")

    def test_reddit(self):
        ch = RedditChannel()
        assert ch.can_handle("https://www.reddit.com/r/python/comments/1")
        assert ch.can_handle("https://old.reddit.com/r/python")
        assert not ch.can_handle("https://x.com/y")

    def test_facebook(self):
        ch = FacebookChannel()
        assert ch.can_handle("https://www.facebook.com/page")
        assert ch.can_handle("https://fb.com/page")

    def test_instagram(self):
        assert InstagramChannel().can_handle("https://instagram.com/user")

    def test_linkedin(self):
        assert LinkedInChannel().can_handle("https://www.linkedin.com/in/user")


class TestSearchCapability:
    def test_twitter_supports_search_flag(self):
        assert TwitterChannel().supports_search is True

    def test_readonly_channels_reject_search(self, cfg):
        for cls in (FacebookChannel, InstagramChannel, LinkedInChannel):
            with pytest.raises(SearchNotSupportedError):
                cls().search("q", cfg)


class TestBackendsDeclared:
    def test_expected_backends(self):
        assert TwitterChannel().backends == ["twitter-cli", "OpenCLI"]
        assert RedditChannel().backends == ["OpenCLI", "rdt-cli"]
        assert FacebookChannel().backends == ["OpenCLI"]


class TestCheckNoBackend:
    def test_warns_with_setup_hint_when_nothing_installed(self, cfg, monkeypatch):
        # No CLI on PATH and OpenCLI absent -> every probe returns None -> WARN.
        monkeypatch.setattr(
            "social_dive.channels._social.probe_command",
            lambda binary, argv, **k: type(
                "R", (), {"ok": False, "error": f"'{binary}' not found on PATH"}
            )(),
        )
        monkeypatch.setattr(
            "social_dive.backends.opencli.opencli_status",
            lambda *a, **k: __import__(
                "social_dive.backends.opencli", fromlist=["OpenCLIStatus"]
            ).OpenCLIStatus(installed=False),
        )
        st = TwitterChannel().check(cfg)
        assert st.level.value == "warn"
        assert "throwaway" in st.message.lower()
