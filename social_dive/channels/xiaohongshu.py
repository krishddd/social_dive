"""
Xiaohongshu (RED / Little Red Book) channel (login-gated).

Reads notes via OpenCLI (browser session) or `xhs-cli` (cookies). Xiaohongshu
has one of the most aggressive anti-scraping stacks (dynamic signing tokens, IP
geofencing), so reverse-engineered CLIs need frequent patching.

⚠️ ToS / BAN RISK: bans quickly under load (~10-20 req/min). Use a throwaway
account and very low volume.
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
class XiaohongshuChannel(CliRoutingChannel):
    name = "xiaohongshu"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["OpenCLI", "xhs-cli"]
    supports_search = True
    setup_hint = (
        "Set up OpenCLI, or install xhs-cli with a cookie (import via "
        "`social-dive configure --from-browser`). Use a throwaway account."
    )

    _URL_PATTERNS = [r"(?:^|//)(?:www\.)?xiaohongshu\.com/", r"(?:^|//)xhslink\.com/"]

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        if backend == "OpenCLI":
            return opencli_backend_probe()
        if backend == "xhs-cli":
            return cli_backend_probe("xhs", ["--version"], "xhs-cli")
        return None

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        if backend == "OpenCLI":
            return ["opencli", "read", url]
        if backend == "xhs-cli":
            return ["xhs", "read", url, "--json"]
        return None

    def _search_argv(
        self, query: str, backend: str, config: Config, limit: int
    ) -> list[str] | None:
        if backend == "xhs-cli":
            return ["xhs", "search", query, "-n", str(limit), "--json"]
        return None
