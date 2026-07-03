"""
Twitter / X channel (login-gated).

Reads tweets and searches via an external backend — `twitter-cli` (needs a
logged-in session / cookies), or OpenCLI reusing the browser session. There is
no official free API path.

⚠️ ToS / BAN RISK: automated access violates X's terms and gets accounts
banned. Use a throwaway account and keep volume low.
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
class TwitterChannel(CliRoutingChannel):
    name = "twitter"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["twitter-cli", "OpenCLI"]
    supports_search = True
    setup_hint = (
        "Install twitter-cli (pipx install twitter-cli) and authenticate, or set up "
        "OpenCLI to reuse your browser session. Use a throwaway account."
    )

    _URL_PATTERNS = [r"(?:^|//)(?:www\.)?(?:x|twitter)\.com/"]

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        if backend == "twitter-cli":
            return cli_backend_probe("twitter", ["status"], "twitter-cli")
        if backend == "OpenCLI":
            return opencli_backend_probe()
        return None

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        if backend == "twitter-cli":
            return ["twitter", "read", url, "--json"]
        if backend == "OpenCLI":
            return ["opencli", "read", url]
        return None

    def _search_argv(
        self, query: str, backend: str, config: Config, limit: int
    ) -> list[str] | None:
        if backend == "twitter-cli":
            return ["twitter", "search", query, "-n", str(limit), "--json"]
        return None
