"""
Tests for the social-connector infrastructure: environment detection, OpenCLI
probing, cookie extraction, and the CliRoutingChannel base. Everything is
mocked — no real browsers, CLIs, or network.
"""

from __future__ import annotations

import pytest

from social_dive.backends import opencli as oc
from social_dive.channels import ChannelTier, StatusLevel
from social_dive.channels._social import (
    CliRoutingChannel,
    content_from_cli_output,
)
from social_dive.config import Config
from social_dive.probe import ProbeResult

# --- environment detection --------------------------------------------------

class TestEnvironment:
    def test_ssh_is_server(self, monkeypatch):
        from social_dive import env
        monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 22 5.6.7.8 22")
        monkeypatch.setattr(env.os.path, "exists", lambda p: False)
        monkeypatch.setattr(env.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        assert env.detect_environment() == "server"

    def test_clean_desktop_is_local(self, monkeypatch):
        from social_dive import env
        monkeypatch.delenv("SSH_CONNECTION", raising=False)
        monkeypatch.delenv("SSH_CLIENT", raising=False)
        monkeypatch.setattr(env.os, "name", "nt")  # Windows desktop
        monkeypatch.setattr(env.os.path, "exists", lambda p: False)
        monkeypatch.setattr(env.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
        assert env.detect_environment() == "local"


# --- OpenCLI probe ----------------------------------------------------------

class TestOpenCLI:
    def test_not_installed(self, monkeypatch):
        monkeypatch.setattr(
            oc, "probe_command",
            lambda *a, **k: ProbeResult(
                ok=False, backend="opencli", error="'opencli' not found on PATH"
            ),
        )
        st = oc.opencli_status()
        assert not st.installed
        assert not st.ready

    def test_installed_but_broken(self, monkeypatch):
        monkeypatch.setattr(
            oc, "probe_command",
            lambda *a, **k: ProbeResult(ok=False, backend="opencli", error="exit code 1"),
        )
        st = oc.opencli_status()
        assert st.installed and st.broken and not st.ready

    def test_ready_when_extension_connected(self, monkeypatch):
        def fake_probe(cmd, args, **k):
            if "--version" in args:
                return ProbeResult(ok=True, backend="opencli", version="1.2.3")
            return ProbeResult(
                ok=True, backend="opencli",
                raw_output="Daemon: running (PID 1)\nExtension: connected",
            )
        monkeypatch.setattr(oc, "probe_command", fake_probe)
        st = oc.opencli_status()
        assert st.installed and st.ready and st.extension_connected


# --- cookie extraction ------------------------------------------------------

class TestCookieExtract:
    def test_unsupported_browser(self):
        from social_dive import cookie_extract
        with pytest.raises(ValueError, match="Unsupported browser"):
            cookie_extract.extract_all("netscape")

    def test_matches_named_platform_cookies(self, monkeypatch):
        from social_dive import cookie_extract
        fake = [
            cookie_extract._Cookie("auth_token", "AAA", ".x.com"),
            cookie_extract._Cookie("ct0", "BBB", ".x.com"),
            cookie_extract._Cookie("irrelevant", "z", ".example.com"),
        ]
        monkeypatch.setattr(cookie_extract, "_load_cookies", lambda browser: fake)
        out = cookie_extract.extract_all("chrome")
        assert out["twitter_cookie"] == {"auth_token": "AAA", "ct0": "BBB"}

    def test_full_cookie_string_platform(self, monkeypatch):
        from social_dive import cookie_extract
        fake = [
            cookie_extract._Cookie("a", "1", ".xiaohongshu.com"),
            cookie_extract._Cookie("b", "2", ".xiaohongshu.com"),
        ]
        monkeypatch.setattr(cookie_extract, "_load_cookies", lambda browser: fake)
        out = cookie_extract.extract_all("chrome")
        assert out["xiaohongshu_cookie"]["cookie_string"] == "a=1; b=2"


# --- CliRoutingChannel base -------------------------------------------------

class _DummyChannel(CliRoutingChannel):
    name = "dummy"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["toolA", "toolB"]
    _URL_PATTERNS = [r"dummy\.test"]
    setup_hint = "install toolA"

    def __init__(self, probes=None, read_ok=True):
        self._probes = probes or {}
        self._read_ok = read_ok

    def _backend_probe(self, backend, config):
        return self._probes.get(backend)

    def _read_argv(self, url, backend, config):
        return ["echo", url] if self._read_ok else None


@pytest.fixture
def cfg(tmp_path):
    return Config(config_dir=tmp_path / ".sd")


class TestCliRoutingChannel:
    def test_can_handle(self, cfg):
        assert _DummyChannel().can_handle("https://dummy.test/x")
        assert not _DummyChannel().can_handle("https://other.com")

    def test_check_warns_when_no_backend(self, cfg):
        st = _DummyChannel(probes={}).check(cfg)
        assert st.level == StatusLevel.WARN
        assert "install toolA" in st.message

    def test_check_picks_ok_backend(self, cfg):
        ch = _DummyChannel(probes={"toolB": (StatusLevel.OK, "ready")})
        st = ch.check(cfg)
        assert st.level == StatusLevel.OK
        assert st.active_backend == "toolB"

    def test_read_not_ready_is_structured(self, cfg):
        content = _DummyChannel(probes={}).read("https://dummy.test/x", cfg)
        assert content.error_code == "unauthenticated"

    def test_read_shells_out_when_backend_live(self, cfg, monkeypatch):
        ch = _DummyChannel(probes={"toolA": (StatusLevel.OK, "ready")})
        monkeypatch.setattr(
            "social_dive.channels._social.run_cli",
            lambda argv, timeout=60.0: (0, '{"title": "Hi", "text": "body"}', ""),
        )
        content = ch.read("https://dummy.test/x", cfg)
        assert content.error_code is None
        assert content.title == "Hi"
        assert content.backend == "toolA"


class TestContentFromCliOutput:
    def test_json_output_mapped(self):
        c = content_from_cli_output("u", "ch", "b", '{"title": "T", "author": "A"}')
        assert c.title == "T"
        assert c.authors == ["A"]

    def test_plain_text_becomes_body(self):
        c = content_from_cli_output("u", "ch", "b", "just some text")
        assert c.body == "just some text"
        assert c.title == ""
