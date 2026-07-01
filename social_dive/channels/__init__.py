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
    """Structured content returned by a channel read()."""
    title: str = ""
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    body: str = ""
    url: str = ""
    source_channel: str = ""
    published_date: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

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
        }


@dataclass
class SearchResult:
    """A single search result from a channel."""
    title: str = ""
    url: str = ""
    snippet: str = ""
    source_channel: str = ""
    authors: list[str] = field(default_factory=list)
    published_date: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

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
        }


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
