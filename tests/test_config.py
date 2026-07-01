"""
Config module tests — file creation, permissions, env-var override, key management.
"""

from __future__ import annotations

import os
import platform
import stat
from pathlib import Path

import pytest

from social_dive.config import Config


@pytest.fixture
def config_dir(tmp_path):
    """Create a temporary config directory."""
    d = tmp_path / ".social-dive-test"
    return d


class TestConfig:
    def test_create_and_read(self, config_dir):
        cfg = Config(config_dir=config_dir)
        cfg.set("test_key", "test_value")
        assert cfg.get("test_key") == "test_value"

    def test_config_file_created(self, config_dir):
        cfg = Config(config_dir=config_dir)
        cfg.set("key", "val")
        assert (config_dir / "config.yaml").exists()

    @pytest.mark.skipif(platform.system() == "Windows", reason="POSIX permissions only")
    def test_file_permissions_posix(self, config_dir):
        cfg = Config(config_dir=config_dir)
        cfg.set("secret", "s3cr3t")
        perms = oct(os.stat(config_dir / "config.yaml").st_mode & 0o777)
        assert perms == "0o600"

    def test_env_var_override(self, config_dir, monkeypatch):
        cfg = Config(config_dir=config_dir)
        cfg.set("llm_provider", "openai")
        monkeypatch.setenv("SOCIAL_DIVE_LLM_PROVIDER", "anthropic")
        assert cfg.get("llm_provider") == "anthropic"

    def test_default_values(self, config_dir):
        cfg = Config(config_dir=config_dir)
        assert cfg.get("llm_provider") == "nvidia"  # built-in default
        assert cfg.get("log_level") == "INFO"

    def test_delete_key(self, config_dir):
        cfg = Config(config_dir=config_dir)
        cfg.set("to_delete", "value")
        assert cfg.get("to_delete") == "value"
        assert cfg.delete("to_delete") is True
        assert cfg.get("to_delete") is None

    def test_delete_nonexistent(self, config_dir):
        cfg = Config(config_dir=config_dir)
        assert cfg.delete("nonexistent") is False

    def test_all_config(self, config_dir):
        cfg = Config(config_dir=config_dir)
        cfg.set("nvidia_api_key", "nvapi-test")
        all_cfg = cfg.all()
        assert "nvidia_api_key" in all_cfg
        assert "llm_provider" in all_cfg  # from default

    def test_persistence(self, config_dir):
        cfg1 = Config(config_dir=config_dir)
        cfg1.set("persistent_key", "persistent_value")

        cfg2 = Config(config_dir=config_dir)
        assert cfg2.get("persistent_key") == "persistent_value"
