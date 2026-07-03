"""
OpenCLI backend detection.

OpenCLI (an external, npm-distributed tool) drives the user's already-logged-in
Chrome via a browser extension + local daemon, so login-gated platforms
(Twitter, Reddit, Instagram, …) can be read without handling credentials
ourselves — the session already lives in the browser. This module only *probes*
whether OpenCLI is installed and its daemon/extension are wired up; it never
launches anything.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass

from social_dive.probe import probe_command

OPENCLI_PACKAGE = "opencli"  # npm/pipx-distributed; not pip-installable
OPENCLI_EXTENSION_ID = "opencli"  # placeholder chrome extension id fragment
_CHROME_PROFILE_ROOTS = [
    "~/.config/google-chrome",
    "~/Library/Application Support/Google/Chrome",
]


@dataclass
class OpenCLIStatus:
    """Result of probing OpenCLI's install + daemon/extension state."""
    installed: bool = False
    broken: bool = False
    daemon_running: bool = False
    extension_connected: bool = False
    extension_installed: bool = False
    version: str = ""
    hint: str = ""

    @property
    def ready(self) -> bool:
        """Usable now or on first call.

        A live connection counts, and so does an installed-but-sleeping
        extension: its service worker wakes on the first real command.
        """
        return (
            self.installed
            and not self.broken
            and (self.extension_connected or self.extension_installed)
        )


def opencli_status(timeout: int = 10) -> OpenCLIStatus:
    """Probe OpenCLI install + daemon/extension state without side effects."""
    version_probe = probe_command("opencli", ["opencli", "--version"], timeout=timeout)
    if not version_probe.ok and "not found" in (version_probe.error or "").lower():
        return OpenCLIStatus(installed=False)
    if not version_probe.ok:
        return OpenCLIStatus(
            installed=True,
            broken=True,
            hint="opencli is installed but won't run — reinstall it (npm i -g opencli).",
        )

    st = OpenCLIStatus(installed=True, version=version_probe.version.strip())

    daemon_probe = probe_command(
        "opencli", ["opencli", "daemon", "status"], timeout=timeout
    )
    output = daemon_probe.raw_output if daemon_probe.ok else ""
    for line in output.splitlines():
        low = line.strip().lower()
        if low.startswith("daemon:"):
            st.daemon_running = "not running" not in low and "running" in low
        elif low.startswith("extension:"):
            st.extension_connected = "disconnected" not in low and "connected" in low

    if not st.extension_connected:
        st.extension_installed = _extension_installed_on_disk()
        if not st.extension_installed:
            st.hint = (
                "OpenCLI is installed but the Chrome extension isn't. Install it, "
                "keep Chrome open, then run `opencli doctor` to verify."
            )
    return st


def _extension_installed_on_disk() -> bool:
    """True if the OpenCLI extension appears in any Chrome profile on disk."""
    roots = [os.path.expanduser(p) for p in _CHROME_PROFILE_ROOTS]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:  # Windows
        roots.append(os.path.join(local_app_data, "Google", "Chrome", "User Data"))
    for root in roots:
        if glob.glob(os.path.join(root, "*", "Extensions", OPENCLI_EXTENSION_ID)):
            return True
    return False
