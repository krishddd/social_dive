"""
GitHub channel — search repos, issues, code and read READMEs.

Backends:
  1. gh CLI (if installed and authenticated)
  2. GitHub REST API (with personal access token)

Tier: needs-key (GitHub token for higher rate limits).
"""

from __future__ import annotations

import json as _json
import re
import subprocess

import httpx
from loguru import logger

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
from social_dive.probe import probe_command


@register_channel
class GitHubChannel(Channel):
    name = "github"
    tier = ChannelTier.NEEDS_KEY
    backends = ["gh-cli", "rest-api"]

    _API_BASE = "https://api.github.com"

    _URL_PATTERNS = [
        r"github\.com/",
    ]

    def can_handle(self, url: str) -> bool:
        return self._match_url(url, self._URL_PATTERNS)

    def read(self, url: str, config: Config) -> Content:
        """Read a GitHub repo README or issue."""
        parsed = self._parse_github_url(url)
        if not parsed:
            raise ValueError(f"Could not parse GitHub URL: {url}")

        owner, repo = parsed["owner"], parsed["repo"]
        token = config.get("github_token", "")
        headers = self._make_headers(token)

        if parsed.get("type") == "issue":
            return self._read_issue(owner, repo, parsed["number"], headers, url)
        elif parsed.get("type") == "pull":
            return self._read_issue(owner, repo, parsed["number"], headers, url)
        else:
            return self._read_repo(owner, repo, headers, url)

    def search(self, query: str, config: Config, limit: int = 10) -> list[SearchResult]:
        """Search GitHub repositories."""
        token = config.get("github_token", "")
        headers = self._make_headers(token)

        resp = httpx.get(
            f"{self._API_BASE}/search/repositories",
            params={"q": query, "per_page": limit, "sort": "stars"},
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()

        results: list[SearchResult] = []
        for repo in resp.json().get("items", []):
            results.append(
                SearchResult(
                    title=repo.get("full_name", ""),
                    url=repo.get("html_url", ""),
                    snippet=repo.get("description", "") or "",
                    source_channel=self.name,
                    authors=[repo.get("owner", {}).get("login", "")],
                    score=float(repo.get("stargazers_count", 0)),
                    metadata={
                        "stars": repo.get("stargazers_count", 0),
                        "forks": repo.get("forks_count", 0),
                        "language": repo.get("language", ""),
                        "license": (repo.get("license") or {}).get("spdx_id", ""),
                    },
                )
            )

        return results

    def check(self, config: Config) -> ChannelStatus:
        # Try gh CLI first
        gh_result = probe_command("gh-cli", ["gh", "--version"])
        if gh_result.ok:
            # Check if authenticated
            auth_result = probe_command("gh-cli", ["gh", "auth", "status"], timeout=5.0)
            if auth_result.ok:
                return ChannelStatus(
                    channel=self.name,
                    level=StatusLevel.OK,
                    tier=self.tier,
                    active_backend="gh-cli",
                    message=f"gh CLI authenticated ({gh_result.version})",
                )
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.WARN,
                tier=self.tier,
                active_backend="gh-cli",
                message="gh CLI installed but not authenticated (run 'gh auth login')",
            )

        # Check REST API
        token = config.get("github_token", "")
        if token:
            return ChannelStatus(
                channel=self.name,
                level=StatusLevel.OK,
                tier=self.tier,
                active_backend="rest-api",
                message="GitHub REST API with token",
            )

        return ChannelStatus(
            channel=self.name,
            level=StatusLevel.WARN,
            tier=self.tier,
            message="No GitHub token or gh CLI. Set 'github_token' or install gh CLI.",
        )

    # -- Helpers --

    def _make_headers(self, token: str) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SocialDive/0.1.0",
        }
        if token:
            headers["Authorization"] = f"token {token}"
        return headers

    def _read_repo(self, owner: str, repo: str, headers: dict, url: str) -> Content:
        """Read repo metadata and README."""
        # Get repo info
        resp = httpx.get(f"{self._API_BASE}/repos/{owner}/{repo}", headers=headers, timeout=15.0)
        resp.raise_for_status()
        repo_data = resp.json()

        # Get README
        readme_body = ""
        try:
            readme_resp = httpx.get(
                f"{self._API_BASE}/repos/{owner}/{repo}/readme",
                headers={**headers, "Accept": "application/vnd.github.v3.raw"},
                timeout=15.0,
            )
            if readme_resp.status_code == 200:
                readme_body = readme_resp.text
        except Exception:
            pass

        return Content(
            title=f"{owner}/{repo}",
            authors=[owner],
            abstract=repo_data.get("description", ""),
            body=f"# {owner}/{repo}\n\n"
                 f"*{repo_data.get('description', '')}*\n\n"
                 f"⭐ {repo_data.get('stargazers_count', 0)} stars · "
                 f"🍴 {repo_data.get('forks_count', 0)} forks · "
                 f"📝 {repo_data.get('language', 'Unknown')} · "
                 f"📜 {(repo_data.get('license') or {}).get('spdx_id', 'No license')}\n\n"
                 f"---\n\n{readme_body}",
            url=url,
            source_channel=self.name,
            metadata={
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "language": repo_data.get("language", ""),
                "open_issues": repo_data.get("open_issues_count", 0),
                "default_branch": repo_data.get("default_branch", "main"),
            },
        )

    def _read_issue(self, owner: str, repo: str, number: str, headers: dict, url: str) -> Content:
        """Read an issue or PR."""
        resp = httpx.get(
            f"{self._API_BASE}/repos/{owner}/{repo}/issues/{number}",
            headers=headers,
            timeout=15.0,
        )
        resp.raise_for_status()
        issue = resp.json()

        # Get comments
        comments_body = ""
        try:
            comments_resp = httpx.get(
                f"{self._API_BASE}/repos/{owner}/{repo}/issues/{number}/comments",
                headers=headers,
                params={"per_page": 20},
                timeout=15.0,
            )
            if comments_resp.status_code == 200:
                for c in comments_resp.json():
                    comments_body += f"\n\n---\n**{c.get('user', {}).get('login', 'unknown')}:**\n{c.get('body', '')}"
        except Exception:
            pass

        labels = [l.get("name", "") for l in issue.get("labels", [])]

        return Content(
            title=issue.get("title", ""),
            authors=[issue.get("user", {}).get("login", "")],
            body=f"# {issue.get('title', '')}\n\n"
                 f"*#{number} by {issue.get('user', {}).get('login', '')} · "
                 f"{issue.get('state', 'unknown')} · "
                 f"Labels: {', '.join(labels) if labels else 'none'}*\n\n"
                 f"{issue.get('body', '')}"
                 f"{comments_body}",
            url=url,
            source_channel=self.name,
            published_date=issue.get("created_at", ""),
            metadata={
                "state": issue.get("state", ""),
                "labels": labels,
                "comments_count": issue.get("comments", 0),
            },
        )

    @staticmethod
    def _parse_github_url(url: str) -> dict | None:
        # /owner/repo/issues/123 or /owner/repo/pull/456 or /owner/repo
        match = re.search(r"github\.com/([^/]+)/([^/]+?)(?:/(issues|pull)/(\d+))?(?:[/?#]|$)", url)
        if match:
            result = {"owner": match.group(1), "repo": match.group(2).rstrip(".git")}
            if match.group(3):
                result["type"] = match.group(3)
                result["number"] = match.group(4)
            return result
        return None
