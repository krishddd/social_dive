"""
Reddit channel (login-gated).

Reddit has no zero-config path in 2026 — anonymous JSON endpoints increasingly
403, and new API-app approval is effectively closed. Reads via OpenCLI (browser
session) or `rdt-cli` (cookies).

⚠️ ToS / BAN RISK: automated access can get accounts limited/banned. Use a
throwaway account.
"""

from __future__ import annotations

from social_dive.channels import ChannelTier, StatusLevel
from social_dive.channels._social import (
    CliRoutingChannel,
    cli_backend_probe,
    opencli_backend_probe,
)
from social_dive.config import Config
from social_dive.doctor import register_channel


@register_channel
class RedditChannel(CliRoutingChannel):
    name = "reddit"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["OpenCLI", "rdt-cli"]
    supports_search = True
    setup_hint = (
        "Set up OpenCLI to reuse your browser session, or install rdt-cli with "
        "cookies. There is no anonymous path for Reddit anymore."
    )

    _URL_PATTERNS = [r"(?:^|//)(?:www\.|old\.)?reddit\.com/"]

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        if backend == "OpenCLI":
            return opencli_backend_probe()
        if backend == "rdt-cli":
            return cli_backend_probe("rdt", ["--version"], "rdt-cli")
        return None

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        if backend == "OpenCLI":
            return ["opencli", "read", url]
        if backend == "rdt-cli":
            return ["rdt", "read", url, "--json"]
        return None

    def _search_argv(
        self, query: str, backend: str, config: Config, limit: int
    ) -> list[str] | None:
        if backend == "rdt-cli":
            return ["rdt", "search", query, "-n", str(limit), "--json"]
        return None
