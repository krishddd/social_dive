"""
Real-execution backend prober for Social Dive.

Unlike shutil.which() (which only checks if a binary exists on PATH), this
module actually *runs* the candidate command with a timeout and inspects the
output.  This catches "installed but broken" cases: stale venvs, expired auth,
binaries that exist but segfault, etc.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Sequence

from loguru import logger


@dataclass
class ProbeResult:
    """Outcome of probing a single backend command."""
    ok: bool
    backend: str
    version: str = ""
    error: str = ""
    raw_output: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "backend": self.backend,
            "version": self.version,
            "error": self.error,
        }


def probe_command(
    backend: str,
    args: Sequence[str],
    *,
    timeout: float = 10.0,
    expect_in_output: str | None = None,
) -> ProbeResult:
    """Run a command and determine if the backend is working.

    Parameters
    ----------
    backend
        Identifier for this backend (e.g. "gh", "yt-dlp").
    args
        Full command + arguments to run, e.g. ``["gh", "--version"]``.
    timeout
        Maximum seconds to wait for the command.
    expect_in_output
        If set, stdout must contain this substring for the probe to be
        considered successful (case-insensitive).

    Returns
    -------
    ProbeResult
        With ``ok=True`` if the command ran successfully.
    """
    # Quick check: is the binary even on PATH?
    if not shutil.which(args[0]):
        return ProbeResult(
            ok=False,
            backend=backend,
            error=f"'{args[0]}' not found on PATH",
        )

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            # Don't let the child process inherit our stdin — some CLIs
            # try to prompt interactively otherwise.
            stdin=subprocess.DEVNULL,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        combined = f"{stdout}\n{stderr}"

        if result.returncode != 0:
            return ProbeResult(
                ok=False,
                backend=backend,
                error=f"Exit code {result.returncode}: {stderr or stdout}",
                raw_output=combined,
            )

        if expect_in_output and expect_in_output.lower() not in combined.lower():
            return ProbeResult(
                ok=False,
                backend=backend,
                error=f"Output did not contain expected '{expect_in_output}'",
                raw_output=combined,
            )

        # Try to extract a version string from the first line
        version = stdout.split("\n")[0] if stdout else ""

        return ProbeResult(
            ok=True,
            backend=backend,
            version=version,
            raw_output=combined,
        )

    except subprocess.TimeoutExpired:
        return ProbeResult(
            ok=False,
            backend=backend,
            error=f"Command timed out after {timeout}s",
        )
    except FileNotFoundError:
        return ProbeResult(
            ok=False,
            backend=backend,
            error=f"'{args[0]}' not found",
        )
    except Exception as e:
        return ProbeResult(
            ok=False,
            backend=backend,
            error=f"Unexpected error: {e}",
        )


def probe_python_import(backend: str, module: str) -> ProbeResult:
    """Check if a Python module can be imported.

    This catches cases where a package is listed in pip but its actual import
    fails (missing C extension, broken install, etc.).
    """
    try:
        __import__(module)
        import importlib
        mod = importlib.import_module(module)
        version = getattr(mod, "__version__", getattr(mod, "VERSION", "unknown"))
        return ProbeResult(
            ok=True,
            backend=backend,
            version=str(version),
        )
    except ImportError as e:
        return ProbeResult(
            ok=False,
            backend=backend,
            error=f"Import failed: {e}",
        )
    except Exception as e:
        return ProbeResult(
            ok=False,
            backend=backend,
            error=f"Import error: {e}",
        )


def probe_url(
    backend: str,
    url: str,
    *,
    timeout: float = 10.0,
    expected_status: int = 200,
) -> ProbeResult:
    """Check if an HTTP endpoint is reachable.

    Used for API-based backends where there's no CLI tool to probe.
    """
    try:
        import httpx

        resp = httpx.get(url, timeout=timeout, follow_redirects=True)

        if resp.status_code == expected_status:
            return ProbeResult(
                ok=True,
                backend=backend,
                version=f"HTTP {resp.status_code}",
                raw_output=resp.text[:200],
            )
        else:
            return ProbeResult(
                ok=False,
                backend=backend,
                error=f"HTTP {resp.status_code} (expected {expected_status})",
                raw_output=resp.text[:200],
            )
    except Exception as e:
        return ProbeResult(
            ok=False,
            backend=backend,
            error=f"Connection failed: {e}",
        )
