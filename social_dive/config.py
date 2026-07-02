"""
Secure configuration store for Social Dive.

Reads/writes ~/.social-dive/config.yaml with restrictive file permissions (0600)
from creation.  Supports environment-variable overrides with the SOCIAL_DIVE_ prefix.
"""

from __future__ import annotations

import os
import platform
import stat
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

# ---------------------------------------------------------------------------
# Defaults & constants
# ---------------------------------------------------------------------------

_APP_DIR_NAME = ".social-dive"
_CONFIG_FILE_NAME = "config.yaml"
_ENV_PREFIX = "SOCIAL_DIVE_"

# Keys that the config file can hold.  This also drives env-var lookups:
# e.g. "nvidia_api_key" → SOCIAL_DIVE_NVIDIA_API_KEY
CONFIG_KEYS: list[str] = [
    # LLM
    "llm_provider",       # nvidia | openai | anthropic
    "llm_model",          # model string (e.g. "deepseek-ai/deepseek-v4-flash")
    "nvidia_api_key",
    "openai_api_key",
    "anthropic_api_key",
    # Channel-specific
    "github_token",
    "ncbi_api_key",
    "ncbi_email",
    "openalex_email",
    "openalex_api_key",
    "stackexchange_key",
    "semantic_scholar_api_key",
    # General
    "cache_dir",
    "log_level",
]

# Default values for keys that have sensible defaults
_DEFAULTS: dict[str, Any] = {
    "llm_provider": "nvidia",
    "llm_model": "deepseek-ai/deepseek-v4-flash",
    "log_level": "INFO",
}


# ---------------------------------------------------------------------------
# Config class
# ---------------------------------------------------------------------------

class Config:
    """Read/write Social Dive configuration.

    Resolution order for each key:
      1. Environment variable ``SOCIAL_DIVE_<KEY_UPPER>``
      2. Value in ``~/.social-dive/config.yaml``
      3. Built-in default (if any)
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or (Path.home() / _APP_DIR_NAME)
        self._file = self._dir / _CONFIG_FILE_NAME
        self._data: dict[str, Any] = {}
        self._load()

    # -- public API ---------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value with env-var override and built-in default."""
        # 1. Environment variable
        env_key = f"{_ENV_PREFIX}{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val

        # 2. Config file
        if key in self._data:
            return self._data[key]

        # 3. Built-in default
        if key in _DEFAULTS:
            return _DEFAULTS[key]

        return default

    def set(self, key: str, value: Any) -> None:
        """Set a config value and persist to disk."""
        if key not in CONFIG_KEYS:
            logger.warning(f"Setting unknown config key: {key}")
        self._data[key] = value
        self._save()
        logger.info(f"Config key '{key}' updated")

    def delete(self, key: str) -> bool:
        """Remove a config key.  Returns True if it existed."""
        if key in self._data:
            del self._data[key]
            self._save()
            logger.info(f"Config key '{key}' removed")
            return True
        return False

    def all(self) -> dict[str, Any]:
        """Return all resolved config values (env → file → default)."""
        result: dict[str, Any] = {}
        for key in CONFIG_KEYS:
            val = self.get(key)
            if val is not None:
                result[key] = val
        return result

    @property
    def config_dir(self) -> Path:
        return self._dir

    @property
    def config_file(self) -> Path:
        return self._file

    # -- internal -----------------------------------------------------------

    def _load(self) -> None:
        """Load config from YAML file if it exists."""
        if self._file.exists():
            try:
                with open(self._file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    self._data = data if isinstance(data, dict) else {}
            except Exception as e:
                logger.error(f"Failed to read config file {self._file}: {e}")
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """Persist config to YAML with restrictive file permissions.

        On POSIX systems, the file is created with mode 0600 (owner read/write
        only) using os.open() with O_CREAT — there is no race window where the
        file is world-readable.

        On Windows, os.chmod is best-effort (NTFS ACLs don't map cleanly to
        POSIX modes).
        """
        self._dir.mkdir(parents=True, exist_ok=True)

        yaml_content = yaml.dump(self._data, default_flow_style=False, allow_unicode=True)
        encoded = yaml_content.encode("utf-8")

        if platform.system() != "Windows":
            # POSIX: atomic create with restrictive mode from the start
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            mode = 0o600
            fd = os.open(str(self._file), flags, mode)
            try:
                os.write(fd, encoded)
            finally:
                os.close(fd)
        else:
            # Windows: write normally, then best-effort chmod
            with open(self._file, "wb") as f:
                f.write(encoded)
            try:
                os.chmod(str(self._file), stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                logger.debug("Could not restrict file permissions on Windows (NTFS ACLs)")

    def __repr__(self) -> str:
        return f"Config(dir={self._dir})"
