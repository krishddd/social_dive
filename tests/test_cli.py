"""
CLI integration tests — version sync, help output, basic command execution.
"""

from __future__ import annotations

from social_dive import __version__
from social_dive.cli import main


class TestVersionSync:
    """Version must be consistent across all declaration sites."""

    def test_version_is_semver(self):
        import re
        assert re.match(r"^\d+\.\d+\.\d+", __version__), f"Version '{__version__}' is not semver"

    def test_version_matches_pyproject(self):
        """Version in __init__.py must match pyproject.toml."""
        from pathlib import Path

        import tomllib

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
