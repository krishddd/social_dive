"""
Installer / skill command tests.

All filesystem seams are redirected to tmp_path so nothing touches the real
~/.claude, ~/.agents, or ~/.social-dive:
  - social_dive.cli._skill_dir_candidates -> a temp skills dir
  - social_dive.cli.Config -> a Config rooted at a temp dir

These run on every CI leg including windows-latest, exercising the
Windows-safe skill replacement path (try/except OSError around rmtree) rather
than assuming Unix symlink behavior.
"""

from __future__ import annotations

import pytest

import social_dive.cli as cli
from social_dive.cli import main
from social_dive.config import Config


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Redirect skill dirs and Config into an isolated temp home."""
    claude_home = tmp_path / ".claude"
    claude_home.mkdir()  # agent home must exist for the skill to install
    skills = claude_home / "skills"
    monkeypatch.setattr(cli, "_skill_dir_candidates", lambda: [skills])

    config_dir = tmp_path / ".social-dive"
    monkeypatch.setattr(cli, "Config", lambda: Config(config_dir=config_dir))

    return {
        "skill_target": skills / "social-dive",
        "skill_file": skills / "social-dive" / "SKILL.md",
        "config_file": config_dir / "config.yaml",
        "config_dir": config_dir,
    }


class TestSkillCommand:
    def test_install_copies_skill_md(self, home):
        main(["skill", "--install"])
        assert home["skill_file"].exists()
        assert "social-dive" in home["skill_file"].read_text(encoding="utf-8")

    def test_uninstall_removes_skill(self, home):
        main(["skill", "--install"])
        assert home["skill_target"].exists()
        main(["skill", "--uninstall"])
        assert not home["skill_target"].exists()

    def test_reinstall_replaces_existing(self, home):
        main(["skill", "--install"])
        # A stale extra file in the target must not survive a reinstall.
        stale = home["skill_target"] / "stale.txt"
        stale.write_text("old", encoding="utf-8")
        main(["skill", "--install"])
        assert home["skill_file"].exists()
        assert not stale.exists()


class TestInstallDryRunSafe:
    def test_dry_run_makes_no_changes(self, home):
        main(["install", "--dry-run"])
        assert not home["skill_target"].exists()
        assert not home["config_file"].exists()

    def test_safe_makes_no_changes(self, home):
        main(["install", "--safe"])
        assert not home["skill_target"].exists()
        assert not home["config_file"].exists()

    def test_normal_install_creates_config_and_skill(self, home, monkeypatch):
        # Pretend all deps are present so no real pip runs during the test.
        monkeypatch.setattr(cli, "_missing_channel_deps", lambda channels: [])
        main(["install"])
        assert home["config_file"].exists()
        assert home["skill_file"].exists()

    def test_install_never_pip_installs_outside_allowlist(self, home, monkeypatch):
        """The package passed to pip must come only from the fixed allow-list."""
        calls: list[str] = []
        monkeypatch.setattr(cli, "_pip_install", lambda pkg: calls.append(pkg))
        monkeypatch.setattr(
            cli, "_missing_channel_deps", lambda channels: [("pubmed", "biopython")]
        )
        main(["install"])
        assert calls == ["biopython"]


class TestUninstallCommand:
    def _seed(self, home):
        main(["skill", "--install"])
        Config(config_dir=home["config_dir"]).set("llm_provider", "nvidia")

    def test_uninstall_removes_skill_and_config(self, home, monkeypatch):
        self._seed(home)
        assert home["skill_target"].exists()
        assert home["config_file"].exists()
        main(["uninstall"])
        assert not home["skill_target"].exists()
        assert not home["config_dir"].exists()

    def test_keep_config_preserves_config(self, home):
        self._seed(home)
        main(["uninstall", "--keep-config"])
        assert not home["skill_target"].exists()
        assert home["config_file"].exists()

    def test_dry_run_removes_nothing(self, home):
        self._seed(home)
        main(["uninstall", "--dry-run"])
        assert home["skill_target"].exists()
        assert home["config_file"].exists()


class TestMissingDeps:
    def test_present_dep_not_flagged(self, monkeypatch):
        monkeypatch.setattr(
            cli, "probe_python_import",
            lambda pkg, mod: type("R", (), {"ok": True})(),
        )
        assert cli._missing_channel_deps(["arxiv"]) == []

    def test_absent_dep_flagged(self, monkeypatch):
        monkeypatch.setattr(
            cli, "probe_python_import",
            lambda pkg, mod: type("R", (), {"ok": False})(),
        )
        assert cli._missing_channel_deps(["arxiv"]) == [("arxiv", "arxiv")]

    def test_channel_without_dep_is_skipped(self, monkeypatch):
        # 'github' needs no extra pip dep, so it's never flagged.
        assert cli._missing_channel_deps(["github"]) == []
