"""
CLI entry point for Social Dive.

Usage:
    social-dive version
    social-dive doctor [--json]
    social-dive configure <key> <value>
    social-dive configure --list
    social-dive read <url> [--format=markdown|json] [--summarize]
    social-dive search <query> [--channels=arxiv,github,...] [--limit=10] [--format=markdown|json]
    social-dive summarize <url> [--prompt="..."]
    social-dive install [--channels=...] [--safe] [--dry-run]
    social-dive uninstall [--keep-config]
    social-dive skill --install | --uninstall
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console

from social_dive import __version__
from social_dive.config import Config

if TYPE_CHECKING:
    from social_dive.channels import Content
    from social_dive.core import SocialDive

console = Console()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="social-dive",
        description="🤿 Social Dive — AI-agent internet-access layer for 20+ knowledge sources",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set log verbosity",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # -- version ---
    sub.add_parser("version", help="Show version")

    # -- doctor ---
    doc = sub.add_parser("doctor", help="Health-check all channels")
    doc.add_argument("--json", action="store_true", help="Output as JSON")

    # -- configure ---
    cfg = sub.add_parser("configure", help="Get/set configuration values")
    cfg.add_argument("key", nargs="?", help="Config key to set")
    cfg.add_argument("value", nargs="?", help="Config value")
    cfg.add_argument("--list", action="store_true", help="List all config values")
    cfg.add_argument("--delete", action="store_true", help="Delete a config key")

    # -- read ---
    read = sub.add_parser("read", help="Read content from one or more URLs")
    read.add_argument("url", nargs="+", help="URL(s) to read (multiple fetched concurrently)")
    read.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
        help="Output format (default: markdown)",
    )
    read.add_argument("--summarize", action="store_true", help="LLM-summarize the content")

    # -- search ---
    search = sub.add_parser("search", help="Search across channels")
    search.add_argument("query", help="Search query")
    search.add_argument("--channels", default=None, help="Comma-separated channel list")
    search.add_argument("--limit", type=int, default=10, help="Max results per channel")
    search.add_argument(
        "--format", choices=["markdown", "json"], default="markdown",
        help="Output format",
    )

    # -- summarize ---
    summ = sub.add_parser("summarize", help="LLM-powered content summary")
    summ.add_argument("url", help="URL to summarize")
    summ.add_argument("--prompt", default=None, help="Custom summarization prompt")

    # -- install ---
    inst = sub.add_parser("install", help="Install dependencies")
    inst.add_argument("--channels", default=None, help="Comma-separated channel list")
    inst.add_argument("--safe", action="store_true", help="Print instructions only, no mutation")
    inst.add_argument("--dry-run", action="store_true", help="Preview only")

    # -- uninstall ---
    uninst = sub.add_parser("uninstall", help="Remove Social Dive data")
    uninst.add_argument("--keep-config", action="store_true", help="Keep config file")

    # -- skill ---
    skill = sub.add_parser("skill", help="Manage agent skill files")
    skill_group = skill.add_mutually_exclusive_group(required=True)
    skill_group.add_argument("--install", action="store_true", help="Install skill files")
    skill_group.add_argument("--uninstall", action="store_true", help="Remove skill files")

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_version(args: argparse.Namespace) -> None:
    console.print(f"🤿 Social Dive v{__version__}")


def _cmd_doctor(args: argparse.Namespace) -> None:
    from social_dive.doctor import check_all, print_report

    config = Config()
    report = check_all(config)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)


def _cmd_configure(args: argparse.Namespace) -> None:
    config = Config()

    if args.list or (args.key is None and not args.delete):
        # List all config
        all_cfg = config.all()
        if not all_cfg:
            console.print(
                "[dim]No configuration set. Use 'social-dive configure <key> <value>'[/dim]"
            )
            return
        for k, v in sorted(all_cfg.items()):
            # Mask sensitive values
            display_v = v
            if "key" in k.lower() or "token" in k.lower():
                display_v = str(v)[:8] + "..." if len(str(v)) > 8 else v
            console.print(f"  [cyan]{k}[/cyan] = {display_v}")
        return

    if args.delete:
        if not args.key:
            console.print("[red]Specify a key to delete[/red]")
            return
        if config.delete(args.key):
            console.print(f"  [green]Deleted '{args.key}'[/green]")
        else:
            console.print(f"  [yellow]Key '{args.key}' not found in config[/yellow]")
        return

    if args.key and args.value:
        config.set(args.key, args.value)
        console.print(f"  [green]Set '{args.key}'[/green]")
    elif args.key:
        val = config.get(args.key)
        if val is not None:
            console.print(f"  [cyan]{args.key}[/cyan] = {val}")
        else:
            console.print(f"  [dim]{args.key} is not set[/dim]")


def _cmd_read(args: argparse.Namespace) -> None:
    from social_dive.core import SocialDive

    sd = SocialDive()

    # args.url is always a list (nargs="+"). A single URL keeps the exact
    # original single-read output; multiple URLs fetch concurrently.
    if len(args.url) == 1:
        _render_read(sd, sd.read(args.url[0]), args)
        return

    contents = sd.read_many(args.url)
    if args.format == "json":
        print(json.dumps([c.to_dict() for c in contents], indent=2, ensure_ascii=False))
        return
    for i, content in enumerate(contents):
        if i:
            console.print("\n" + "─" * 60)
        _render_read(sd, content, args)


def _render_read(sd: SocialDive, content: Content, args: argparse.Namespace) -> None:
    if content.error_code:
        console.print(f"[red]Read failed ({content.error_code}): {content.body}[/red]")
        if args.format != "json":
            return

    if args.format == "json":
        print(json.dumps(content.to_dict(), indent=2, ensure_ascii=False))
    else:
        # Markdown output
        if content.title:
            console.print(f"\n# {content.title}\n")
        if content.authors:
            console.print(f"*{', '.join(content.authors)}*\n")
        if content.abstract:
            console.print(f"> {content.abstract}\n")
        if content.body:
            console.print(content.body)

    if args.summarize:
        summary = sd.summarize(content)
        console.print(f"\n---\n## Summary\n\n{summary}")


def _cmd_search(args: argparse.Namespace) -> None:
    from social_dive.core import SocialDive

    channels = args.channels.split(",") if args.channels else None
    sd = SocialDive()
    response = sd.search(args.query, channels=channels, limit=args.limit)

    if args.format == "json":
        print(json.dumps(response.to_dict(), indent=2, ensure_ascii=False))
    else:
        if not response.results:
            console.print("[dim]No results found.[/dim]")
        for i, r in enumerate(response.results, 1):
            console.print(f"\n[bold]{i}. {r.title}[/bold]")
            console.print(f"   [dim]{r.source_channel}[/dim] · {r.url}")
            if r.snippet:
                console.print(f"   {r.snippet[:200]}")
        if response.skipped:
            console.print("\n[dim]Skipped:[/dim]")
            for channel_name, reason in response.skipped.items():
                console.print(f"   [dim]{channel_name}: {reason}[/dim]")


def _cmd_summarize(args: argparse.Namespace) -> None:
    from social_dive.core import SocialDive

    sd = SocialDive()
    content = sd.read(args.url)
    summary = sd.summarize(content, prompt=args.prompt)
    console.print(f"\n## Summary of: {content.title or args.url}\n\n{summary}")


def _cmd_install(args: argparse.Namespace) -> None:
    console.print("[yellow]Install command is not yet implemented in this version.[/yellow]")
    console.print("Run 'social-dive doctor' to see which channels are available.")


def _cmd_uninstall(args: argparse.Namespace) -> None:
    console.print("[yellow]Uninstall command is not yet implemented in this version.[/yellow]")


def _cmd_skill(args: argparse.Namespace) -> None:
    console.print("[yellow]Skill management is not yet implemented in this version.[/yellow]")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_COMMANDS = {
    "version": _cmd_version,
    "doctor": _cmd_doctor,
    "configure": _cmd_configure,
    "read": _cmd_read,
    "search": _cmd_search,
    "summarize": _cmd_summarize,
    "install": _cmd_install,
    "uninstall": _cmd_uninstall,
    "skill": _cmd_skill,
}


def main(argv: Sequence[str] | None = None) -> None:
    """Main CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = args.log_level or "WARNING"
    logger.remove()
    logger.add(sys.stderr, level=log_level, format="<level>{message}</level>")

    if args.command is None:
        parser.print_help()
        return

    handler = _COMMANDS.get(args.command)
    if handler:
        try:
            handler(args)
        except KeyboardInterrupt:
            console.print("\n[dim]Interrupted.[/dim]")
            sys.exit(130)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.exception("Command failed")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
