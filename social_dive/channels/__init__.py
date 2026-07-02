"""
Abstract base class for all Social Dive channels.

Every channel (arXiv, GitHub, YouTube, etc.) subclasses ``Channel`` and implements
the four required methods.  The ``backends`` list drives the ordered-fallback
pattern: the first working backend is used, with automatic failover to the next.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from social_dive.config import Config

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ChannelTier(str, Enum):
    """Classification of how much setup a channel needs."""
    ZERO_CONFIG = "zero-config"
    NEEDS_KEY = "needs-key"
    NEEDS_TOOL = "needs-tool"


class StatusLevel(str, Enum):
    """Health-check status for a channel."""
    OK = "ok"
    WARN = "warn"
    OFF = "off"
    ERROR = "error"


@dataclass
class ChannelStatus:
    """Result of a channel health check."""
    channel: str
    level: StatusLevel
    tier: ChannelTier
    active_backend: str = ""
    message: str = ""
    backends_checked: dict[str, str] = field(default_factory=dict)  # backend → status msg


@dataclass
class Content:
    """Structured content returned by a channel read().

    ``backend`` records which of the channel's ``backends`` actually served
    this result (e.g. "yt-dlp" vs "youtube-transcript-api"), and
    ``error_code`` is set by the core dispatcher — never by the channel
    itself — when ``read()`` raised, so a broken channel degrades to a
    structured result instead of propagating an exception. Allowed values:
    "rate_limited", "unauthenticated", "timeout", "not_found", "error".
    """
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    body: str = ""
    url: str = ""
    source_channel: str = ""
    published_date: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    backend: str = ""
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "body": self.body,
            "url": self.url,
            "source_channel": self.source_channel,
            "published_date": self.published_date,
            "metadata": self.metadata,
            "fetched_at": self.fetched_at,
            "backend": self.backend,
            "error_code": self.error_code,
        }


@dataclass
class SearchResult:
    """A single search result from a channel.

    ``backend`` records which of the channel's ``backends`` produced this
    result. ``fetched_at`` is stamped centrally by the core dispatcher (not
    per-channel) so every result in one search response shares a consistent
    retrieval timestamp.
    """
    title: str = ""
    url: str = ""
    snippet: str = ""
    source_channel: str = ""
    authors: list[str] = field(default_factory=list)
    published_date: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    backend: str = ""
    fetched_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_channel": self.source_channel,
            "authors": self.authors,
            "published_date": self.published_date,
            "score": self.score,
            "metadata": self.metadata,
            "backend": self.backend,
            "fetched_at": self.fetched_at,
        }


class SearchNotSupportedError(Exception):
    """Raised by ``Channel.search()`` when a channel has no search capability.

    Distinguishes "search not implemented for this source" from "searched
    and found zero results" — per BrowseComp research (arXiv:2504.12516),
    an agent needs this signal to know whether reformulating the query is
    worth trying, rather than seeing an ambiguous empty list either way.
    """


# ---------------------------------------------------------------------------
# Abstract Channel base
# ---------------------------------------------------------------------------

class Channel(ABC):
    """Abstract base class for all Social Dive channels.

    Subclasses MUST define:
      - ``name``: short identifier (e.g. "arxiv", "github")
      - ``tier``: how much setup is needed
      - ``backends``: ordered list of backend identifiers

    And implement all four abstract methods.
    """

    name: str
    tier: ChannelTier
    backends: list[str]

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Return True if this channel can handle the given URL."""
        ...

    @abstractmethod
    def read(self, url: str, config: Config) -> Content:
        """Fetch and return structured content from the URL."""
        ...

    @abstractmethod
    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search this channel and return results."""
        ...

    @abstractmethod
    def check(self, config: Config) -> ChannelStatus:
        """Probe this channel's backends and return a health-check status."""
        ...

    def _match_url(self, url: str, patterns: list[str]) -> bool:
        """Helper: check if a URL matches any of the given regex patterns."""
        for pattern in patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    def __repr__(self) -> str:
        return f"<Channel:{self.name} tier={self.tier.value} backends={self.backends}>"
