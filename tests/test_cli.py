"""
CLI integration tests — version sync, help output, basic command execution,
the Windows UTF-8 stdio fix, and check-update.
"""

from __future__ import annotations

import io
import sys

from social_dive import __version__
from social_dive.cli import _force_utf8_stdio, _version_tuple, main


class TestVersionSync:
    """Version must be consistent across all declaration sites."""

    def test_version_is_semver(self):
        import re
        assert re.match(r"^\d+\.\d+\.\d+", __version__), f"Version '{__version__}' is not semver"

    def test_version_matches_pyproject(self):
        """Version in __init__.py must match pyproject.toml."""
        from pathlib import Path

        try:
            import tomllib  # Python 3.11+
        except ModuleNotFoundError:
            import tomli as tomllib  # Python 3.10 backport — CI tests 3.10 too

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        if pyproject.exists():
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            assert data["project"]["version"] == __version__


class TestCLI:
    def test_help_exits_cleanly(self, capsys):
        """Running with no args should print help and not crash."""
        main([])
        # Help is printed to stdout or stderr depending on argparse
        # Just verify it doesn't crash

    def test_version_command(self, capsys):
        main(["version"])
        captured = capsys.readouterr()
        assert __version__ in captured.out

    def test_configure_list_empty(self, tmp_path, capsys):
        """Configure --list on empty config should not crash."""
        import os
        os.environ["SOCIAL_DIVE_LLM_PROVIDER"] = "nvidia"
        main(["configure", "--list"])
        # Should produce some output without crashing


class TestUtf8Stdio:
    """Regression: rich output (the 🤿 emoji) must not crash on a legacy
    Windows console using cp1252 — the bug was a UnicodeEncodeError."""

    def test_reconfigures_cp1252_stream_to_utf8(self, monkeypatch):
        raw = io.BytesIO()
        wrapper = io.TextIOWrapper(raw, encoding="cp1252")
        monkeypatch.setattr(sys, "stdout", wrapper)
        monkeypatch.setattr(sys, "stderr", wrapper)

        _force_utf8_stdio()

        assert sys.stdout.encoding.lower() == "utf-8"
        sys.stdout.write("🤿")  # would raise UnicodeEncodeError under cp1252
        sys.stdout.flush()
        assert "🤿".encode() in raw.getvalue()

    def test_safe_on_stream_without_reconfigure(self, monkeypatch):
        # A stream lacking reconfigure() (e.g. a plain StringIO) must be a no-op.
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        _force_utf8_stdio()  # must not raise


class _Resp:
    def __init__(self, status: int, payload: dict | None = None):
        self.status_code = status
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


def _patch_pypi(monkeypatch, resp: _Resp) -> None:
    class _Client:
        def get(self, *a, **k):
            return resp

    monkeypatch.setattr("social_dive.http_client.get_client", lambda config=None: _Client())


class TestCheckUpdate:
    def test_version_tuple(self):
        assert _version_tuple("0.2.0") == (0, 2, 0)
        assert _version_tuple("v1.10.3rc1") == (1, 10, 3)

    def test_up_to_date(self, monkeypatch, capsys):
        _patch_pypi(monkeypatch, _Resp(200, {"info": {"version": __version__}}))
        main(["check-update"])
        assert "up to date" in capsys.readouterr().out.lower()

    def test_update_available(self, monkeypatch, capsys):
        _patch_pypi(monkeypatch, _Resp(200, {"info": {"version": "999.0.0"}}))
        main(["check-update"])
        assert "update available" in capsys.readouterr().out.lower()

    def test_not_on_pypi_is_graceful(self, monkeypatch, capsys):
        _patch_pypi(monkeypatch, _Resp(404))
        main(["check-update"])
        assert "not published" in capsys.readouterr().out.lower()
