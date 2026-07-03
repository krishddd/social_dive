"""
LinkedIn channel (login-gated, read-only via browser session).

⚠️ ToS / BAN RISK: LinkedIn actively detects automation and (per 2026 reports)
suspends flagged sessions quickly. Use a throwaway account and keep volume very
low — a handful of profiles/day at most.
"""

from __future__ import annotations

from social_dive.channels import ChannelTier, StatusLevel
from social_dive.channels._social import CliRoutingChannel, opencli_backend_probe
from social_dive.config import Config
from social_dive.doctor import register_channel


@register_channel
class LinkedInChannel(CliRoutingChannel):
    name = "linkedin"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["OpenCLI"]
    supports_search = False
    setup_hint = (
        "Set up OpenCLI to reuse your logged-in browser session. LinkedIn bans "
        "aggressively — use a throwaway account and very low volume."
    )

    _URL_PATTERNS = [r"(?:^|//)(?:www\.)?linkedin\.com/"]

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        return opencli_backend_probe() if backend == "OpenCLI" else None

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        return ["opencli", "read", url] if backend == "OpenCLI" else None
