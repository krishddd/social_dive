"""
Shared base for login-gated social channels.

These platforms have no clean public API, so — like the reference project, and
consistent with this repo's "glue/routing layer" rule — each channel *routes*
to an external backend (a platform CLI, or OpenCLI reusing the browser's login
session) rather than reimplementing the scraping. This base handles the common
shape: probe the ordered backends, pick the best one (two-pass), and shell out;
when nothing is set up, return a structured `unauthenticated`/`restricted`
result with setup guidance instead of raising.

ToS / BAN RISK: automated access to these platforms violates their terms and can
get accounts banned. Use throwaway accounts, keep volume low, and treat this as
opt-in tooling. `check()` surfaces this; it never accesses anything on its own.
"""

from __future__ import annotations

import json
import subprocess

from loguru import logger

from social_dive.channels import (
    Channel,
    ChannelStatus,
    Content,
    SearchNotSupportedError,
    SearchResult,
    StatusLevel,
)
from social_dive.config import Config
from social_dive.probe import probe_command


def cli_backend_probe(
    binary: str, probe_args: list[str] | None = None, label: str | None = None
) -> tuple[StatusLevel, str] | None:
    """Probe a platform CLI. None = not installed; OK if it runs; WARN otherwise."""
    result = probe_command(binary, [binary, *(probe_args or ["--version"])])
    if not result.ok and "not found" in (result.error or "").lower():
        return None
    name = label or binary
    if result.ok:
        return StatusLevel.OK, f"{name} available"
    return StatusLevel.WARN, f"{name} installed but not ready: {result.error}"


def opencli_backend_probe() -> tuple[StatusLevel, str] | None:
    """Map OpenCLI's probed state to a (level, message). None = not installed."""
    from social_dive.backends import opencli_status

    st = opencli_status()
    if not st.installed:
        return None
    if st.broken:
        return StatusLevel.ERROR, st.hint or "OpenCLI is installed but broken."
    if st.ready:
        return StatusLevel.OK, "OpenCLI ready (reuses your logged-in browser session)"
    return StatusLevel.WARN, st.hint or "OpenCLI installed — connect the Chrome extension."


def run_cli(argv: list[str], timeout: float = 60.0) -> tuple[int, str, str]:
    """Run a backend CLI, returning (returncode, stdout, stderr).

    Never raises for process failures — a missing binary or timeout maps to a
    non-zero return code so callers can degrade to a structured result.
    """
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", f"{argv[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]}: timed out after {timeout}s"
    except OSError as e:
        return 1, "", str(e)


def content_from_cli_output(url: str, channel: str, backend: str, stdout: str) -> Content:
    """Build a Content from a backend CLI's stdout.

    If stdout is JSON with recognizable fields, map them; otherwise the raw text
    becomes the body. The source URL is always the caller's verbatim URL.
    """
    stdout = stdout.strip()
    title, body, authors, published = "", stdout, [], ""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        data = None
    if isinstance(data, dict):
        title = str(data.get("title") or data.get("name") or "")
        body = str(
            data.get("text") or data.get("content") or data.get("body") or stdout
        )
        author = data.get("author") or data.get("user") or data.get("uploader")
        if author:
            authors = [str(author)]
        published = str(data.get("date") or data.get("published") or data.get("created_at") or "")
    return Content(
        title=title,
        authors=authors,
        body=body,
        url=url,
        source_channel=channel,
        backend=backend,
        published_date=published,
        metadata={"raw_backend_output": bool(data is None)},
    )


class CliRoutingChannel(Channel):
    """Base for channels that route to an external CLI / OpenCLI backend."""

    _URL_PATTERNS: list[str] = []
    #: Shown when no backend is set up (should tell the user how to fix it).
    setup_hint: str = "No backend is set up for this channel."
    #: Whether the platform supports query search at all.
    supports_search: bool = True

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    # -- subclass hooks -----------------------------------------------------

    def _backend_probe(self, backend: str, config: Config) -> tuple[StatusLevel, str] | None:
        """Probe one backend. Return (level, message), or None if unavailable."""
        raise NotImplementedError

    def _read_argv(self, url: str, backend: str, config: Config) -> list[str] | None:
        """argv to read ``url`` via ``backend`` (None if it can't)."""
        return None

    def _search_argv(
        self, query: str, backend: str, config: Config, limit: int
    ) -> list[str] | None:
        """argv to search via ``backend`` (None if it can't)."""
        return None

    # -- Channel interface --------------------------------------------------

    def _candidates(self, config: Config) -> list[tuple[str, StatusLevel, str]]:
        found: list[tuple[str, StatusLevel, str]] = []
        for backend in self.ordered_backends(config):
            probe = self._backend_probe(backend, config)
            if probe is not None:
                found.append((backend, probe[0], probe[1]))
        return found

    def check(self, config: Config) -> ChannelStatus:
        chosen = self.select_backend(self._candidates(config))
        if chosen is None:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.WARN,
                tier=self.tier,
                message=self.setup_hint,
            )
        backend, level, message = chosen
        return ChannelStatus(
            channel=self.name,
            level=level,
            tier=self.tier,
            active_backend=backend,
            message=message,
        )

    def _live_backend(self, config: Config) -> str | None:
        """The first fully-usable (OK) backend, or None."""
        chosen = self.select_backend(self._candidates(config))
        if chosen and chosen[1] == StatusLevel.OK:
            return chosen[0]
        return None

    def read(self, url: str, config: Config) -> Content:
        backend = self._live_backend(config)
        if backend is None:
            return self._not_ready(url)
        argv = self._read_argv(url, backend, config)
        if argv is None:
            return self._not_ready(url)
        rc, out, err = run_cli(argv)
        if rc != 0:
            logger.debug(f"{self.name} read via {backend} failed (rc={rc}): {err}")
            return Content(
                url=url,
                source_channel=self.name,
                backend=backend,
                body=f"[{self.name} read failed via {backend}: {err.strip() or rc}]",
                error_code="error",
            )
        return content_from_cli_output(url, self.name, backend, out)

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        if not self.supports_search:
            raise SearchNotSupportedError(
                f"{self.name} has no query search; read a specific URL instead"
            )
        backend = self._live_backend(config)
        if backend is None:
            raise SearchNotSupportedError(
                f"{self.name} search needs a backend set up — run "
                "`social-dive doctor` to see how"
            )
        argv = self._search_argv(query, backend, config, limit)
        if argv is None:
            raise SearchNotSupportedError(f"{self.name} backend '{backend}' can't search")
        rc, out, _ = run_cli(argv)
        if rc != 0:
            return []
        return self._parse_search(out, backend)

    def _parse_search(self, stdout: str, backend: str) -> list[SearchResult]:
        """Parse backend search stdout (JSON array of items) into results."""
        try:
            data = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            return []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("results", [])
        else:
            items = []
        results: list[SearchResult] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or item.get("text") or "")[:200],
                    url=str(item.get("url") or item.get("link") or ""),
                    snippet=str(item.get("snippet") or item.get("text") or "")[:300],
                    source_channel=self.name,
                    backend=backend,
                    metadata={k: item[k] for k in ("score", "date") if k in item},
                )
            )
        return results

    def _not_ready(self, url: str) -> Content:
        return Content(
            url=url,
            source_channel=self.name,
            body=f"[{self.name} needs a login-gated backend set up. {self.setup_hint}]",
            error_code="unauthenticated",
        )
