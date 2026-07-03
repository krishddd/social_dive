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
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console

from social_dive import __version__
from social_dive.config import Config
from social_dive.probe import probe_python_import

if TYPE_CHECKING:
    from social_dive.channels import Content
    from social_dive.core import SocialDive


def _force_utf8_stdio() -> None:
    """Force stdout/stderr to UTF-8 so rich output can't crash the CLI.

    The default Windows console uses a legacy code page (e.g. cp1252) that
    can't encode the emoji/box-drawing characters in our `rich` output, so a
    bare `social-dive version` would raise UnicodeEncodeError. Reconfiguring to
    UTF-8 with errors="replace" makes output robust everywhere; it's a no-op on
    platforms that are already UTF-8. Runs before the module-level Console is
    created so the Console binds to the reconfigured streams.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # detached/closed stream — ignore
                pass


_force_utf8_stdio()
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

    # -- check-update ---
    sub.add_parser("check-update", help="Check whether a newer version is available")

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
    uninst.add_argument("--dry-run", action="store_true", help="Preview only")

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


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def _cmd_check_update(args: argparse.Namespace) -> None:
    """Compare the installed version against the latest published on PyPI."""
    from social_dive.http_client import get_client

    try:
        resp = get_client().get(
            "https://pypi.org/pypi/social-dive/json", timeout=10.0, use_cache=False
        )
    except Exception as e:  # noqa: BLE001 — network is best-effort
        console.print(f"[yellow]Could not check for updates: {e}[/yellow]")
        return

    if resp.status_code == 404:
        console.print(
            f"[dim]social-dive {__version__} — not published to PyPI yet, "
            "so there's no newer release to compare against.[/dim]"
        )
        return
    if resp.status_code != 200:
        console.print(f"[yellow]Update check failed: HTTP {resp.status_code}[/yellow]")
        return

    latest = resp.json().get("info", {}).get("version", "")
    if not latest:
        console.print("[yellow]Could not determine the latest version.[/yellow]")
        return

    if _version_tuple(__version__) >= _version_tuple(latest):
        console.print(f"[green]social-dive {__version__} is up to date (latest: {latest}).[/green]")
    else:
        console.print(
            f"[yellow]Update available: {__version__} → {latest}. "
            "Upgrade with:  pip install -U social-dive[/yellow]"
        )


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


# ---------------------------------------------------------------------------
# install / uninstall / skill
# ---------------------------------------------------------------------------

# Fixed, pinned allow-list: channel -> (import_name, pip_package). ONLY these
# package names are ever passed to `pip install` — never anything derived from
# user or network input — so the installer can't become an injection surface.
# Channels not listed here need no extra dependency (they use the httpx core).
_CHANNEL_PIP_DEPS: dict[str, tuple[str, str]] = {
    "arxiv": ("arxiv", "arxiv"),
    "rss": ("feedparser", "feedparser"),
    "youtube": ("youtube_transcript_api", "youtube-transcript-api"),
    "pubmed": ("Bio", "biopython"),
}


def _skill_source() -> Path:
    """Path to the packaged SKILL.md."""
    return Path(__file__).resolve().parent / "skill" / "SKILL.md"


def _skill_dir_candidates() -> list[Path]:
    """Agent skill directories to install into, in priority order.

    Factored out so tests can monkeypatch it to a temp location.
    """
    home = Path.home()
    return [home / ".claude" / "skills", home / ".agents" / "skills"]


def _install_skill(dry_run: bool = False) -> list[Path]:
    """Copy SKILL.md into each agent home that exists. Returns targets touched."""
    src = _skill_source()
    installed: list[Path] = []
    for base in _skill_dir_candidates():
        # Only install where the agent home (base.parent, e.g. ~/.claude) exists.
        if not base.parent.exists():
            continue
        target = base / "social-dive"
        if dry_run:
            console.print(f"  [dim][dry-run] would install skill -> {target}[/dim]")
            installed.append(target)
            continue
        # Windows-safe replace: rmtree can raise on junctions / locked files or
        # where symlink semantics differ — treat "can't remove" as "preserve".
        if target.exists():
            try:
                shutil.rmtree(target)
            except OSError as e:
                console.print(f"  [yellow]Could not replace {target}: {e}; preserving[/yellow]")
                continue
        try:
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target / "SKILL.md")
            installed.append(target)
            console.print(f"  [green]Installed skill -> {target}[/green]")
        except OSError as e:
            console.print(f"  [yellow]Could not install skill to {target}: {e}[/yellow]")
    if not installed and not dry_run:
        console.print(
            "  [dim]No agent home (~/.claude, ~/.agents) found — skill not installed.[/dim]"
        )
    return installed


def _uninstall_skill(dry_run: bool = False) -> list[Path]:
    """Remove the social-dive skill from every agent home. Returns targets touched."""
    removed: list[Path] = []
    for base in _skill_dir_candidates():
        target = base / "social-dive"
        if not target.exists():
            continue
        if dry_run:
            console.print(f"  [dim][dry-run] would remove {target}[/dim]")
            removed.append(target)
            continue
        try:
            shutil.rmtree(target)
            removed.append(target)
            console.print(f"  [green]Removed skill from {target}[/green]")
        except OSError as e:
            console.print(f"  [yellow]Could not remove {target}: {e}[/yellow]")
    return removed


def _pip_install(pkg: str) -> None:
    """Run `pip install <pkg>` for a package from the fixed allow-list only."""
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)
    except (subprocess.CalledProcessError, OSError) as e:
        console.print(f"  [yellow]pip install {pkg} failed: {e}[/yellow]")


def _missing_channel_deps(channels: list[str] | None) -> list[tuple[str, str]]:
    """Return (channel, pip_package) for each requested channel whose dep is absent."""
    targets = channels if channels else list(_CHANNEL_PIP_DEPS.keys())
    missing: list[tuple[str, str]] = []
    for channel in targets:
        dep = _CHANNEL_PIP_DEPS.get(channel)
        if dep is None:
            continue
        import_name, pip_pkg = dep
        if not probe_python_import(pip_pkg, import_name).ok:
            missing.append((channel, pip_pkg))
    return missing


def _cmd_install(args: argparse.Namespace) -> None:
    dry_run: bool = args.dry_run
    safe: bool = args.safe
    channels = args.channels.split(",") if args.channels else None

    missing = _missing_channel_deps(channels)
    if not missing:
        console.print("[green]All requested channel dependencies are already installed.[/green]")
    else:
        pkgs = sorted({pip_pkg for _, pip_pkg in missing})
        if dry_run:
            console.print(f"[dry-run] Would install: {', '.join(pkgs)}")
        elif safe:
            console.print("Missing channel dependencies. Install them with:")
            console.print(f"  {sys.executable} -m pip install {' '.join(pkgs)}")
        else:
            for pkg in pkgs:
                console.print(f"  Installing {pkg} ...")
                _pip_install(pkg)

    # Config skeleton + skill registration only mutate in normal mode.
    if dry_run:
        console.print(f"[dry-run] Would ensure config at {Config().config_file}")
        _install_skill(dry_run=True)
        console.print("Dry run complete. No changes were made.")
    elif safe:
        console.print("Then create your config and register the skill:")
        console.print("  social-dive configure <key> <value>")
        console.print("  social-dive skill --install")
    else:
        _ensure_config_skeleton()
        _install_skill()


def _ensure_config_skeleton() -> None:
    cfg = Config()
    if cfg.config_file.exists():
        console.print(f"[dim]Config already exists at {cfg.config_file}[/dim]")
        return
    # Persisting the default provider creates the 0600 config file.
    cfg.set("llm_provider", cfg.get("llm_provider", "nvidia"))
    console.print(f"  [green]Created config at {cfg.config_file}[/green]")


def _cmd_uninstall(args: argparse.Namespace) -> None:
    dry_run: bool = args.dry_run
    _uninstall_skill(dry_run=dry_run)

    cfg = Config()
    if args.keep_config:
        console.print(f"[dim]Keeping config at {cfg.config_dir}[/dim]")
    elif dry_run:
        console.print(f"[dry-run] Would remove config directory {cfg.config_dir}")
    elif cfg.config_dir.exists():
        try:
            shutil.rmtree(cfg.config_dir)
            console.print(f"  [green]Removed {cfg.config_dir}[/green]")
        except OSError as e:
            console.print(f"  [yellow]Could not remove {cfg.config_dir}: {e}[/yellow]")

    if dry_run:
        console.print("Dry run complete. No changes were made.")


def _cmd_skill(args: argparse.Namespace) -> None:
    if args.install:
        _install_skill()
    else:  # --uninstall (mutually exclusive group, required)
        _uninstall_skill()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

_COMMANDS = {
    "version": _cmd_version,
    "check-update": _cmd_check_update,
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
