"""
Health-check aggregator for Social Dive.

Loops all registered channels, calls ``channel.check(config)``, catches
per-channel exceptions (a broken channel must never take down the whole report),
and renders a tiered status report.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from rich.console import Console
from rich.table import Table

from social_dive.channels import Channel, ChannelStatus, ChannelTier, StatusLevel
from social_dive.config import Config


# ---------------------------------------------------------------------------
# Channel registry
# ---------------------------------------------------------------------------

# All Channel subclasses discovered at import time
_CHANNEL_REGISTRY: list[type[Channel]] = []


def register_channel(cls: type[Channel]) -> type[Channel]:
    """Decorator: register a Channel subclass in the global registry."""
    _CHANNEL_REGISTRY.append(cls)
    return cls


def get_registered_channels() -> list[type[Channel]]:
    """Return all registered channel classes."""
    return list(_CHANNEL_REGISTRY)


def _discover_channels() -> None:
    """Import all modules in social_dive.channels to trigger @register_channel."""
    import social_dive.channels as channels_pkg

    for _importer, modname, _ispkg in pkgutil.iter_modules(channels_pkg.__path__):
        if modname == "base":
            continue
        try:
            importlib.import_module(f"social_dive.channels.{modname}")
        except Exception as e:
            logger.debug(f"Could not import channel module '{modname}': {e}")


# ---------------------------------------------------------------------------
# Doctor report
# ---------------------------------------------------------------------------

@dataclass
class DoctorReport:
    """Aggregated health-check report across all channels."""
    channels: list[ChannelStatus] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(s.level == StatusLevel.OK for s in self.channels)

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {level.value: 0 for level in StatusLevel}
        for s in self.channels:
            counts[s.level.value] += 1
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "channels": [
                {
                    "channel": s.channel,
                    "level": s.level.value,
                    "tier": s.tier.value,
                    "active_backend": s.active_backend,
                    "message": s.message,
                    "backends_checked": s.backends_checked,
                }
                for s in self.channels
            ],
            "summary": self.summary,
            "errors": self.errors,
        }


def check_all(config: Config | None = None) -> DoctorReport:
    """Run health checks on all registered channels.

    Each channel is checked independently — a failure in one channel does not
    affect the others.
    """
    if config is None:
        config = Config()

    # Ensure all channel modules are imported
    _discover_channels()

    report = DoctorReport()

    for channel_cls in _CHANNEL_REGISTRY:
        try:
            channel = channel_cls()
            status = channel.check(config)
            report.channels.append(status)
        except Exception as e:
            error_msg = f"Channel '{channel_cls.name}' check crashed: {e}"
            logger.error(error_msg)
            report.errors.append(error_msg)
            report.channels.append(
                ChannelStatus(
                    channel=getattr(channel_cls, "name", channel_cls.__name__),
                    level=StatusLevel.ERROR,
                    tier=getattr(channel_cls, "tier", ChannelTier.ZERO_CONFIG),
                    message=str(e),
                )
            )

    # Sort: ok first, then warn, off, error
    order = {StatusLevel.OK: 0, StatusLevel.WARN: 1, StatusLevel.OFF: 2, StatusLevel.ERROR: 3}
    report.channels.sort(key=lambda s: (order.get(s.level, 9), s.channel))

    return report


def print_report(report: DoctorReport) -> None:
    """Render the doctor report as a rich table to the console."""
    console = Console()

    table = Table(
        title="🤿 Social Dive — Doctor Report",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Channel", style="bold")
    table.add_column("Status")
    table.add_column("Tier", style="dim")
    table.add_column("Backend")
    table.add_column("Details")

    level_style = {
        StatusLevel.OK: "[green]✓ ok[/green]",
        StatusLevel.WARN: "[yellow]⚠ warn[/yellow]",
        StatusLevel.OFF: "[dim]○ off[/dim]",
        StatusLevel.ERROR: "[red]✗ error[/red]",
    }

    for s in report.channels:
        table.add_row(
            s.channel,
            level_style.get(s.level, s.level.value),
            s.tier.value,
            s.active_backend or "—",
            s.message or "—",
        )

    console.print(table)

    # Summary line
    summary = report.summary
    parts = []
    if summary.get("ok"):
        parts.append(f"[green]{summary['ok']} ok[/green]")
    if summary.get("warn"):
        parts.append(f"[yellow]{summary['warn']} warn[/yellow]")
    if summary.get("off"):
        parts.append(f"[dim]{summary['off']} off[/dim]")
    if summary.get("error"):
        parts.append(f"[red]{summary['error']} error[/red]")
    console.print(f"\n  Summary: {' · '.join(parts)}")

    if report.errors:
        console.print(f"\n  [red]Errors during check:[/red]")
        for err in report.errors:
            console.print(f"    • {err}")
