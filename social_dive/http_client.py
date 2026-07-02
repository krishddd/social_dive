"""
Shared, polite HTTP client for Social Dive's API-backed channels.

Social Dive fans out across 10+ free-tier public APIs (Crossref, OpenAlex,
Europe PMC, Stack Exchange, DEV.to, ...), each with its own independent rate
limit. Documented best practice for that shape is a *per-host* token-bucket
limiter plus an on-disk response cache that honours each API's own
``Retry-After`` / ``X-Rate-Limit-*`` headers and ``ETag`` / ``Last-Modified``
revalidation — one reusable core-layer client rather than per-channel logic.

This module provides exactly that. It is deliberately a thin wrapper over
``httpx.Client``: ``get()`` returns a real ``httpx.Response`` so existing
channel code (``resp.json()`` / ``resp.text`` / ``raise_for_status()``) works
unchanged.
"""

from __future__ import annotations

import threading
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from loguru import logger

try:  # diskcache is a declared dependency, but degrade gracefully if absent
    import diskcache

    _HAS_DISKCACHE = True
except ImportError:  # pragma: no cover - exercised only in broken installs
    _HAS_DISKCACHE = False

# Conservative defaults — each is per-host, not global.
_DEFAULT_TTL = 3600.0          # 1h for responses lacking their own cache headers
_DEFAULT_RATE = 5.0            # requests/sec per host
_DEFAULT_BURST = 10            # token-bucket capacity per host
_MAX_RETRY_WAIT = 30.0         # cap on honouring a server's Retry-After
_DEFAULT_TIMEOUT = 15.0
_USER_AGENT = "SocialDive/0.2.0 (+https://github.com/krishddd/social_dive)"


class TokenBucket:
    """Thread-safe token bucket. One instance per host.

    Refills at ``rate`` tokens/sec up to ``capacity``; ``acquire()`` blocks
    only as long as needed for one token to be available, and never holds the
    lock while sleeping so concurrent callers to the same host queue fairly.
    """

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self.capacity, self._tokens + (now - self._last) * self.rate
                )
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait = (1 - self._tokens) / self.rate
            time.sleep(wait)


class HTTPClient:
    """Rate-limited, caching HTTP client shared across API channels."""

    def __init__(
        self,
        config: Any = None,
        *,
        cache_dir: str | Path | None = None,
        default_ttl: float = _DEFAULT_TTL,
        rate: float = _DEFAULT_RATE,
        burst: float = _DEFAULT_BURST,
        rate_limit: bool = True,
        cache: bool = True,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
            transport=transport,
        )
        self._timeout = timeout
        self._rate = rate
        self._burst = burst
        self._rate_limit_enabled = rate_limit
        self._default_ttl = default_ttl
        self._buckets: dict[str, TokenBucket] = {}
        self._buckets_lock = threading.Lock()

        self._cache: Any = None
        if cache and _HAS_DISKCACHE:
            # Finally puts the previously-unused `cache_dir` config key to work.
            resolved = cache_dir
            if resolved is None and config is not None:
                resolved = config.get("cache_dir")
            if resolved is None:
                resolved = Path.home() / ".social-dive" / "http-cache"
            try:
                # diskcache handles concurrent multi-process access via its own
                # file locking, so two agent processes sharing this dir is safe.
                self._cache = diskcache.Cache(str(resolved))
            except Exception as e:  # pragma: no cover - disk/permission edge
                logger.debug(f"HTTP cache disabled (could not open {resolved}): {e}")
                self._cache = None

    # -- public API ---------------------------------------------------------

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        ttl: float | None = None,
        use_cache: bool = True,
    ) -> httpx.Response:
        """GET a URL through the cache + rate limiter, returning a Response.

        Cache flow: a fresh cached entry is returned without any network call;
        a stale entry with an ``ETag``/``Last-Modified`` is revalidated with a
        conditional request (a ``304`` refreshes it in place); anything else is
        fetched live and stored if it's a cacheable ``200``.
        """
        request_headers = dict(headers or {})
        cache_key = self._cache_key("GET", url, params)
        caching = use_cache and self._cache is not None

        entry: dict[str, Any] | None = None
        if caching:
            entry = self._cache.get(cache_key)
            if entry is not None:
                if time.time() < entry["expires_at"]:
                    logger.debug(f"http cache hit (fresh): {url}")
                    return self._response_from_entry(entry, url)
                # Stale — attach validators so the server can answer 304.
                if entry.get("etag"):
                    request_headers.setdefault("If-None-Match", entry["etag"])
                if entry.get("last_modified"):
                    request_headers.setdefault("If-Modified-Since", entry["last_modified"])

        if self._rate_limit_enabled:
            self._bucket_for(url).acquire()

        resp = self._request_with_retry(
            "GET", url, params=params, headers=request_headers, timeout=timeout
        )

        if resp.status_code == 304 and entry is not None:
            logger.debug(f"http cache revalidated (304): {url}")
            entry["expires_at"] = time.time() + self._entry_ttl(resp, ttl)
            if caching:
                self._cache.set(cache_key, entry)
            return self._response_from_entry(entry, url)

        if caching and resp.status_code == 200:
            self._store(cache_key, resp, ttl)

        return resp

    def close(self) -> None:
        self._client.close()
        if self._cache is not None:
            self._cache.close()

    # -- internals ----------------------------------------------------------

    def _bucket_for(self, url: str) -> TokenBucket:
        host = urlparse(url).netloc or url
        with self._buckets_lock:
            bucket = self._buckets.get(host)
            if bucket is None:
                bucket = TokenBucket(self._rate, self._burst)
                self._buckets[host] = bucket
            return bucket

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str],
        timeout: float | None,
        max_retries: int = 2,
    ) -> httpx.Response:
        attempt = 0
        while True:
            resp = self._client.request(
                method,
                url,
                params=params,
                headers=headers,
                timeout=timeout if timeout is not None else self._timeout,
            )
            if resp.status_code in (429, 503) and attempt < max_retries:
                wait = self._retry_after_seconds(resp)
                if wait is not None and wait <= _MAX_RETRY_WAIT:
                    logger.warning(
                        f"{resp.status_code} from {url}; honouring Retry-After={wait:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue
            return resp

    @staticmethod
    def _retry_after_seconds(resp: httpx.Response) -> float | None:
        """Seconds to wait before retrying, from Retry-After or X-Rate-Limit-*.

        Reads the server's own throttling signal rather than assuming a fixed
        sleep: ``Retry-After`` (delta-seconds or HTTP-date) takes priority,
        then an ``X-RateLimit-Reset`` epoch/delta paired with a zeroed
        remaining count.
        """
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    when = parsedate_to_datetime(retry_after)
                    return max(0.0, when.timestamp() - time.time())
                except (TypeError, ValueError):
                    pass

        # Header names vary by vendor (X-RateLimit-* vs X-Rate-Limit-*).
        remaining = _first_header(resp, "X-RateLimit-Remaining", "X-Rate-Limit-Remaining")
        reset = _first_header(resp, "X-RateLimit-Reset", "X-Rate-Limit-Reset")
        if remaining == "0" and reset:
            try:
                reset_val = float(reset)
            except ValueError:
                return None
            # Heuristic: a large value is an absolute epoch; small is a delta.
            delta = reset_val - time.time() if reset_val > 1_000_000_000 else reset_val
            return max(0.0, delta)
        return None

    def _entry_ttl(self, resp: httpx.Response, ttl: float | None) -> float:
        if ttl is not None:
            return ttl
        cache_control = resp.headers.get("Cache-Control", "")
        for directive in cache_control.split(","):
            directive = directive.strip().lower()
            if directive.startswith("max-age="):
                try:
                    return float(directive.split("=", 1)[1])
                except ValueError:
                    break
        return self._default_ttl

    def _store(self, cache_key: str, resp: httpx.Response, ttl: float | None) -> None:
        # ``resp.content`` is already decompressed by httpx, so the stored
        # bytes must not keep transfer/encoding headers that describe the
        # original compressed wire form — otherwise reconstructing the cached
        # Response would make httpx try to decode plain bytes again.
        headers = {
            k: v
            for k, v in resp.headers.items()
            if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
        }
        entry = {
            "status": resp.status_code,
            "headers": headers,
            "content": resp.content,
            "etag": resp.headers.get("ETag"),
            "last_modified": resp.headers.get("Last-Modified"),
            "expires_at": time.time() + self._entry_ttl(resp, ttl),
        }
        try:
            self._cache.set(cache_key, entry)
        except Exception as e:  # pragma: no cover - disk edge
            logger.debug(f"Could not cache {resp.url}: {e}")

    @staticmethod
    def _response_from_entry(entry: dict[str, Any], url: str) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(
            status_code=entry["status"],
            headers=entry["headers"],
            content=entry["content"],
            request=request,
        )

    @staticmethod
    def _cache_key(method: str, url: str, params: dict[str, Any] | None) -> str:
        if params:
            query = urlencode(sorted(params.items()))
            return f"{method}:{url}?{query}"
        return f"{method}:{url}"


def _first_header(resp: httpx.Response, *names: str) -> str | None:
    for name in names:
        value: str | None = resp.headers.get(name)
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# Process-wide shared client
# ---------------------------------------------------------------------------

_shared: HTTPClient | None = None
_shared_lock = threading.Lock()


def get_client(config: Any = None) -> HTTPClient:
    """Return the process-wide shared client, creating it on first use."""
    global _shared
    if _shared is None:
        with _shared_lock:
            if _shared is None:
                _shared = HTTPClient(config=config)
    return _shared
