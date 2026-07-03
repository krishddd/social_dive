"""
Bilibili channel (login-gated).

Reads videos / subtitles and searches via `bili-cli` (cookies: SESSDATA) or
OpenCLI. yt-dlp lost Bilibili support to anti-bot changes in 2026, so it isn't
used here.

⚠️ ToS / BAN RISK: automated access can trip Bilibili's anti-bot system. Use a
throwaway account and keep volume low.
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
class BilibiliChannel(CliRoutingChannel):
    name = "bilibili"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["bili-cli", "OpenCLI"]
    supports_search = True
    setup_hint = (
        "Install bili-cli with cookies (SESSDATA), or set up OpenCLI. Use a "
        "throwaway account."
    )

    _URL_PATTERNS = [r"(?:^|//)(?:www\.|m\.)?bilibili\.com/", r"(?:^|//)b23\.tv/"]

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        if backend == "bili-cli":
            return cli_backend_probe("bili", ["--version"], "bili-cli")
        if backend == "OpenCLI":
            return opencli_backend_probe()
        return None

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        if backend == "bili-cli":
            return ["bili", "read", url, "--json"]
        if backend == "OpenCLI":
            return ["opencli", "read", url]
        return None

    def _search_argv(
        self, query: str, backend: str, config: Config, limit: int
    ) -> list[str] | None:
        if backend == "bili-cli":
            return ["bili", "search", query, "-n", str(limit), "--json"]
        return None
