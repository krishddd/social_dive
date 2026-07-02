"""
Stack Overflow channel — search and read Q&A via Stack Exchange API.

Backend: Stack Exchange API v2.3 (free, optional app key for higher quota).
Tier: needs-key (optional).
"""

from __future__ import annotations

import re
from html import unescape

from social_dive.channels import (
    Channel,
    ChannelStatus,
    ChannelTier,
    Content,
    SearchResult,
    StatusLevel,
)
from social_dive.config import Config
from social_dive.doctor import register_channel
from social_dive.http_client import get_client
from social_dive.probe import probe_url


@register_channel
class StackOverflowChannel(Channel):
    name = "stack_overflow"
    tier = ChannelTier.NEEDS_KEY
    backends = ["stackexchange-api"]

    _API_BASE = "https://api.stackexchange.com/2.3"

    _URL_PATTERNS = [
        r"stackoverflow\.com/questions/",
        r"stackoverflow\.com/q/",
        r"stackoverflow\.com/a/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Read a Stack Overflow question and its answers."""
        question_id = self._extract_question_id(url)
        if not question_id:
            raise ValueError(f"Could not extract SO question ID from: {url}")

        params = self._make_params(config)
        params.update({
            "site": "stackoverflow",
            "filter": "withbody",
        })

        # Get question
        client = get_client(config)
        resp = client.get(
            f"{self._API_BASE}/questions/{question_id}",
            params=params,
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            raise ValueError(f"No SO question found for ID: {question_id}")

        q = items[0]
        q_title = unescape(q.get("title", ""))
        q_body = self._strip_html(q.get("body", ""))
        q_author = q.get("owner", {}).get("display_name", "unknown")
        q_score = q.get("score", 0)
        tags = q.get("tags", [])

        # Get answers
        answers_resp = client.get(
            f"{self._API_BASE}/questions/{question_id}/answers",
            params={**params, "sort": "votes", "order": "desc"},
            timeout=15.0,
        )
        answers_resp.raise_for_status()

        answers_body = ""
        for a in answers_resp.json().get("items", [])[:5]:  # Top 5 answers
            a_author = a.get("owner", {}).get("display_name", "unknown")
            a_body = self._strip_html(a.get("body", ""))
            a_score = a.get("score", 0)
            accepted = " ✅" if a.get("is_accepted") else ""
            answers_body += (
                f"\n\n---\n### Answer by {a_author} (score: {a_score}){accepted}\n\n{a_body}"
            )

        body = (
            f"# {q_title}\n\n"
            f"*Asked by {q_author} · Score: {q_score} · Tags: {', '.join(tags)}*\n\n"
            f"## Question\n\n{q_body}"
            f"\n\n## Answers\n{answers_body}"
        )

        return Content(
            title=q_title,
            authors=[q_author],
            body=body,
            url=url,
            source_channel=self.name,
            backend=self.backends[0],
            metadata={
                "question_id": question_id,
                "score": q_score,
                "tags": tags,
                "answer_count": q.get("answer_count", 0),
                "view_count": q.get("view_count", 0),
                "is_answered": q.get("is_answered", False),
            },
        )

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search Stack Overflow questions."""
        params = self._make_params(config)
        params.update({
            "site": "stackoverflow",
            "order": "desc",
            "sort": "relevance",
            "intitle": query,
            "pagesize": limit,
        })

        resp = get_client(config).get(
            f"{self._API_BASE}/search/advanced",
            params=params,
            timeout=15.0,
        )
        resp.raise_for_status()

        results: list[SearchResult] = []
        for q in resp.json().get("items", []):
            results.append(
                SearchResult(
                    title=unescape(q.get("title", "")),
                    url=q.get("link", ""),
                    snippet=", ".join(q.get("tags", [])),
                    source_channel=self.name,
                    backend=self.backends[0],
                    authors=[q.get("owner", {}).get("display_name", "")],
                    score=float(q.get("score", 0)),
                    metadata={
                        "question_id": q.get("question_id"),
                        "answer_count": q.get("answer_count", 0),
                        "is_answered": q.get("is_answered", False),
                        "view_count": q.get("view_count", 0),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        result = probe_url("stackexchange-api", f"{self._API_BASE}/info?site=stackoverflow")
        if result.ok:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="stackexchange-api",
                message="Stack Exchange API reachable",
            )
        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.ERROR,
            tier=self.tier,
            message=f"Stack Exchange API unreachable: {result.error}",
        )

    def _make_params(self, config: Config) -> dict:
        params: dict = {}
        key = config.get("stackexchange_key")
        if key:
            params["key"] = key
        return params

    @staticmethod
    def _strip_html(html: str) -> str:
        text = re.sub(r"<code>(.*?)</code>", r"`\1`", html, flags=re.DOTALL)
        text = re.sub(r"<pre>(.*?)</pre>", r"\n```\n\1\n```\n", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "", text)
        return unescape(text).strip()

    @staticmethod
    def _extract_question_id(url: str) -> str | None:
        match = re.search(r"/questions/(\d+)", url)
        if not match:
            match = re.search(r"/q/(\d+)", url)
        return match.group(1) if match else None
