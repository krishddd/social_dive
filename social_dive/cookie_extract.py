"""
Browser cookie extraction for cookie-authenticated channels.

Some login-gated platforms (Twitter, Xiaohongshu, Bilibili, Xueqiu) can be read
on a server with the user's exported cookies instead of a live browser session.
This pulls the relevant cookies from a locally installed browser via `rookiepy`
(preferred, Rust-based) or `browser_cookie3`.

SECURITY / SAFETY: cookies are session credentials. Use a throwaway account for
automated access — platforms ban accounts that show automated patterns. Cookies
are only ever written to the 0600 config; never transmitted anywhere by this
tool.
"""

from __future__ import annotations

from typing import Any

# Each platform: which domains to match and which named cookies to capture
# (None = capture all cookies for the domain as a single header string).
PLATFORM_SPECS: list[dict[str, Any]] = [
    {
        "config_key": "twitter_cookie",
        "domains": [".x.com", ".twitter.com"],
        "cookies": ["auth_token", "ct0"],
    },
    {
        "config_key": "xiaohongshu_cookie",
        "domains": [".xiaohongshu.com"],
        "cookies": None,
    },
    {
        "config_key": "bilibili_cookie",
        "domains": [".bilibili.com"],
        "cookies": ["SESSDATA", "bili_jct"],
    },
    {
        "config_key": "xueqiu_cookie",
        "domains": [".xueqiu.com"],
        "cookies": None,
    },
]

SUPPORTED_BROWSERS = ["chrome", "firefox", "edge", "brave", "opera"]


def extract_all(browser: str = "chrome") -> dict[str, dict[str, str]]:
    """Extract known-platform cookies from ``browser``.

    Returns ``{config_key: {cookie_name: value}}`` (or ``{"cookie_string": ...}``
    for platforms that need the full cookie header). Raises RuntimeError if no
    extraction backend is installed, ValueError for an unsupported browser.
    """
    browser = browser.lower()
    if browser not in SUPPORTED_BROWSERS:
        raise ValueError(
            f"Unsupported browser: {browser}. Supported: {', '.join(SUPPORTED_BROWSERS)}"
        )

    cookies = _load_cookies(browser)
    results: dict[str, dict[str, str]] = {}
    for spec in PLATFORM_SPECS:
        results.update(_match_platform(spec, cookies))
    return results


def _load_cookies(browser: str) -> list[Any]:
    """Load all cookies as objects with .name/.value/.domain via rookiepy or bc3."""
    try:
        import rookiepy

        raw = getattr(rookiepy, browser)()
        return [_Cookie(c["name"], c["value"], c["domain"]) for c in raw]
    except ImportError:
        pass

    try:
        import browser_cookie3
    except ImportError as e:
        raise RuntimeError(
            "Cookie extraction needs rookiepy or browser_cookie3.\n"
            "Install:  pip install rookiepy   (recommended)\n"
            "     or:  pip install browser-cookie3"
        ) from e

    jar = getattr(browser_cookie3, browser)()
    return [_Cookie(c.name, c.value, c.domain) for c in jar]


def _match_platform(spec: dict[str, Any], cookies: list[Any]) -> dict[str, dict[str, str]]:
    domains = spec["domains"]
    wanted = spec["cookies"]
    matched = [
        c
        for c in cookies
        if any(c.domain.endswith(d) or c.domain == d.lstrip(".") for d in domains)
    ]
    if not matched:
        return {}

    if wanted is None:
        cookie_string = "; ".join(f"{c.name}={c.value}" for c in matched)
        return {spec["config_key"]: {"cookie_string": cookie_string}}

    named = {c.name: c.value for c in matched if c.name in wanted}
    return {spec["config_key"]: named} if named else {}


class _Cookie:
    __slots__ = ("name", "value", "domain")

    def __init__(self, name: str, value: str, domain: str) -> None:
        self.name = name
        self.value = value
        self.domain = domain
