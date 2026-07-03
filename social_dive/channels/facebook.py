"""
Facebook channel (login-gated, read-only via browser session).

⚠️ ToS / BAN RISK: automated access violates Facebook's terms. Use a throwaway
account and keep volume low.
"""

from __future__ import annotations

from social_dive.channels import ChannelTier, StatusLevel
from social_dive.channels._social import CliRoutingChannel, opencli_backend_probe
from social_dive.config import Config
from social_dive.doctor import register_channel


@register_channel
class FacebookChannel(CliRoutingChannel):
    name = "facebook"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["OpenCLI"]
    supports_search = False
    setup_hint = "Set up OpenCLI to reuse your logged-in browser session. Use a throwaway account."

    _URL_PATTERNS = [r"(?:^|//)(?:www\.|m\.)?facebook\.com/", r"(?:^|//)fb\.com/"]

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        return opencli_backend_probe() if backend == "OpenCLI" else None

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        return ["opencli", "read", url] if backend == "OpenCLI" else None
