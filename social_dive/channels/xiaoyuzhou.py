"""
Xiaoyuzhou (小宇宙) channel — Chinese podcast platform (read-only).

Reads episode pages / show notes via OpenCLI (browser session). Audio
transcription is out of scope here; this returns the episode's text content.

⚠️ ToS: automated access may violate the platform's terms — keep volume low.
"""

from __future__ import annotations

from social_dive.channels import ChannelTier, StatusLevel
from social_dive.channels._social import CliRoutingChannel, opencli_backend_probe
from social_dive.config import Config
from social_dive.doctor import register_channel


@register_channel
class XiaoyuzhouChannel(CliRoutingChannel):
    name = "xiaoyuzhou"
    tier = ChannelTier.NEEDS_TOOL
    backends = ["OpenCLI"]
    supports_search = False
    setup_hint = "Set up OpenCLI to reuse your logged-in browser session."

    _URL_PATTERNS = [r"(?:^|//)(?:www\.)?xiaoyuzhoufm\.com/"]

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        return opencli_backend_probe() if backend == "OpenCLI" else None

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        return ["opencli", "read", url] if backend == "OpenCLI" else None
