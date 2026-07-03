"""
Runtime environment detection.

Login-gated social channels reuse a real, logged-in desktop browser session
(via OpenCLI), which is only viable on a local machine with a display — not on
a headless server. ``detect_environment()`` distinguishes the two so the doctor
and installer can steer server users toward server-friendly backends (platform
CLIs + cookies) instead of the browser-session path.
"""

from __future__ import annotations

import os
import subprocess


def detect_environment() -> str:
    """Return "server" or "local" based on a lightweight indicator score.

    Heuristic (not authoritative): SSH sessions, container markers, missing
    display, and cloud-VM identifiers each add weight; a score >= 2 is treated
    as a headless server. Any probe failure is ignored so detection never
    raises.
    """
    indicators = 0

    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        indicators += 2

    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        indicators += 2

    # No graphical display (X11 / Wayland) — but only meaningful off-Windows,
    # since Windows/macOS desktops don't set these vars.
    if os.name == "posix" and not os.environ.get("DISPLAY") and not os.environ.get(
        "WAYLAND_DISPLAY"
    ):
        indicators += 1

    for cloud_file in ("/sys/hypervisor/uuid", "/sys/class/dmi/id/product_name"):
        try:
            with open(cloud_file, encoding="utf-8", errors="replace") as f:
                content = f.read().lower()
            if any(
                vendor in content
                for vendor in (
                    "amazon", "google", "microsoft", "digitalocean",
                    "linode", "vultr", "hetzner",
                )
            ):
                indicators += 2
        except OSError:
            pass

    try:
        result = subprocess.run(
            ["systemd-detect-virt"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip() not in ("", "none"):
            indicators += 1
    except (OSError, subprocess.SubprocessError):
        pass

    return "server" if indicators >= 2 else "local"
