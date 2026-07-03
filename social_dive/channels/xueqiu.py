"""
Xueqiu (雪球) channel — Chinese investing social network (login-gated).

Reads posts/portfolios via OpenCLI (browser session). Xueqiu gates most content
behind a cookie/login.

⚠️ ToS / BAN RISK: automated access violates Xueqiu's terms. Use a throwaway
account.
"""

from __future__ import annotations

from social_dive.channels import ChannelTier, StatusLevel
from social_dive.channels._social import CliRoutingChannel, opencli_backend_probe
from social_dive.config import Config
from social_dive.doctor import register_channel


@register_channel
class XueqiuChannel(CliRoutingChannel):
    name = "xueqiu"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["OpenCLI"]
    supports_search = False
    setup_hint = (
        "Set up OpenCLI to reuse your logged-in browser session (or import a "
        "cookie via `social-dive configure --from-browser`). Use a throwaway account."
    )

    _URL_PATTERNS = [r"(?:^|//)(?:www\.|xueqiu\.)?xueqiu\.com/"]

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        return opencli_backend_probe() if backend == "OpenCLI" else None

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        return ["opencli", "read", url] if backend == "OpenCLI" else None
