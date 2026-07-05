"""
Shared HTTP client tests — caching, conditional revalidation, Retry-After /
X-Rate-Limit parsing, and token-bucket behavior.

Uses httpx.MockTransport (built into httpx — no extra dependency) so requests
never hit the network, and tmp_path for an isolated on-disk cache. Rate
limiting is disabled in the caching tests so they don't incur real sleeps.
"""

from __future__ import annotations

import time

import httpx
import pytest

from social_dive.http_client import HTTPClient, TokenBucket


class _Handler:
    """A MockTransport handler that records calls and returns queued responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self._responses) == 1:
            return self._responses[0]
        return self._responses.pop(0)

    @property
    def call_count(self) -> int:
        return len(self.requests)


def _make_client(tmp_path, responses, **kwargs):
    handler = _Handler(responses)
    client = HTTPClient(
        cache_dir=tmp_path / "http-cache",
        rate_limit=False,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )
    return client, handler


class TestCaching:
    def test_second_get_served_from_cache(self, tmp_path):
        client, handler = _make_client(
            tmp_path, [httpx.Response(200, json={"x": 1})]
        )
        r1 = client.get("https://api.example.com/data")
        r2 = client.get("https://api.example.com/data")
        assert r1.json() == {"x": 1}
        assert r2.json() == {"x": 1}
        # No cache-validation headers → served fresh from the default TTL, so
        # only one real network call happens.
        assert handler.call_count == 1
        client.close()

    def test_distinct_params_are_cached_separately(self, tmp_path):
        client, handler = _make_client(
            tmp_path, [httpx.Response(200, json={"ok": True})]
        )
        client.get("https://api.example.com/data", params={"q": "a"})
        client.get("https://api.example.com/data", params={"q": "b"})
        assert handler.call_count == 2
        client.close()

    def test_use_cache_false_always_fetches(self, tmp_path):
        client, handler = _make_client(
            tmp_path, [httpx.Response(200, json={"ok": True})]
        )
        client.get("https://api.example.com/data", use_cache=False)
        client.get("https://api.example.com/data", use_cache=False)
        assert handler.call_count == 2
        client.close()

    def test_non_200_not_cached(self, tmp_path):
        client, handler = _make_client(tmp_path, [httpx.Response(500)])
        client.get("https://api.example.com/data")
        client.get("https://api.example.com/data")
        assert handler.call_count == 2
        client.close()


class TestRevalidation:
    def test_stale_entry_revalidates_with_304(self, tmp_path):
        # ttl=0 makes the first entry stale immediately; the second call must
        # send a conditional request and accept the 304 by serving cached body.
        client, handler = _make_client(
            tmp_path,
            [
                httpx.Response(200, json={"x": 1}, headers={"ETag": '"abc"'}),
                httpx.Response(304, headers={"ETag": '"abc"'}),
            ],
        )
        r1 = client.get("https://api.example.com/data", ttl=0)
        r2 = client.get("https://api.example.com/data", ttl=0)
        assert r1.json() == {"x": 1}
        assert r2.json() == {"x": 1}  # body reconstructed from cache on 304
        assert handler.call_count == 2
        # The revalidation request must carry the stored validator.
        assert handler.requests[1].headers.get("If-None-Match") == '"abc"'
        client.close()


class TestContentEncoding:
    def test_cached_gzip_response_reconstructs_without_redecoding(self, tmp_path):
        """Regression: httpx already decompresses resp.content, so a cached
        entry must not keep a Content-Encoding header — otherwise rebuilding
        the Response would make httpx try to gunzip already-plain bytes."""
        client, _ = _make_client(tmp_path, [httpx.Response(200)])
        # A response whose body is already plain but which (mis)declares gzip,
        # as a compressed upstream response looks once httpx has decoded it.
        resp = httpx.Response(
            200,
            content=b'{"x": 1}',
            request=httpx.Request("GET", "https://api.example.com/g"),
        )
        resp.headers["Content-Encoding"] = "gzip"

        client._store("k", resp, None)
        entry = client._cache.get("k")
        assert "content-encoding" not in {h.lower() for h in entry["headers"]}

        rebuilt = client._response_from_entry(entry, "https://api.example.com/g")
        assert rebuilt.json() == {"x": 1}  # would raise DecodingError if kept
        client.close()


class TestRetryAfter:
    def test_429_with_retry_after_is_retried(self, tmp_path):
        client, handler = _make_client(
            tmp_path,
            [
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"ok": True}),
            ],
        )
        r = client.get("https://api.example.com/data")
        assert r.status_code == 200
        assert handler.call_count == 2
        client.close()

    def test_retry_after_delta_seconds(self):
        resp = httpx.Response(
            429,
            headers={"Retry-After": "5"},
            request=httpx.Request("GET", "https://x"),
        )
        assert HTTPClient._retry_after_seconds(resp) == 5.0

    def test_x_ratelimit_reset_as_delta(self):
        resp = httpx.Response(
            429,
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "12"},
            request=httpx.Request("GET", "https://x"),
        )
        assert HTTPClient._retry_after_seconds(resp) == pytest.approx(12, abs=1)

    def test_hyphenated_x_rate_limit_header_variant(self):
        resp = httpx.Response(
            429,
            headers={"X-Rate-Limit-Remaining": "0", "X-Rate-Limit-Reset": "8"},
            request=httpx.Request("GET", "https://x"),
        )
        assert HTTPClient._retry_after_seconds(resp) == pytest.approx(8, abs=1)

    def test_no_throttle_headers_returns_none(self):
        resp = httpx.Response(429, request=httpx.Request("GET", "https://x"))
        assert HTTPClient._retry_after_seconds(resp) is None


class TestProxy:
    def test_reads_http_proxy_from_config(self, tmp_path):
        from social_dive.config import Config

        cfg = Config(config_dir=tmp_path / ".sd")
        cfg.set("http_proxy", "http://127.0.0.1:8888")
        # Construction must succeed and pick up the proxy (no transport given).
        client = HTTPClient(config=cfg, rate_limit=False, cache=False)
        assert client._client._mounts  # httpx records the proxy as a transport mount
        client.close()

    def test_no_proxy_by_default(self, tmp_path):
        from social_dive.config import Config

        client = HTTPClient(config=Config(config_dir=tmp_path / ".sd"), cache=False)
        assert not client._client._mounts
        client.close()


class TestTokenBucket:
    def test_burst_capacity_is_immediate(self):
        tb = TokenBucket(rate=1000.0, capacity=3)
        start = time.monotonic()
        for _ in range(3):
            tb.acquire()
        assert time.monotonic() - start < 0.5

    def test_refill_enforces_wait(self):
        # Capacity 1, 2 tokens/sec: two back-to-back acquires must take ~>=0.3s.
        tb = TokenBucket(rate=2.0, capacity=1)
        tb.acquire()  # consumes the initial token
        start = time.monotonic()
        tb.acquire()  # must wait ~0.5s for a refill
        assert time.monotonic() - start >= 0.3
