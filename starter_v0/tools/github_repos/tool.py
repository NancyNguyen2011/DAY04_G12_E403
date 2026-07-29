from __future__ import annotations

import os
from typing import Any

import requests

from tools._shared import TIMEOUT, err


API = "https://api.github.com/search/repositories"
SORTS = {"stars": "stars", "updated": "updated", "forks": "forks", "relevance": ""}


def _repo_item(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": repo.get("full_name") or "",
        "url": repo.get("html_url") or "",
        "source": "github.com",
        "summary": (repo.get("description") or "").strip(),
        "date": repo.get("pushed_at"),
        "language": repo.get("language"),
        "topics": repo.get("topics") or [],
        "metrics": {
            "stars": repo.get("stargazers_count"),
            "forks": repo.get("forks_count"),
            "open_issues": repo.get("open_issues_count"),
        },
    }


def search_github_repos(query: str = "", sort_by: str = "stars", language: str = "", limit: int = 5) -> dict[str, Any]:
    """Search public GitHub repositories. Unauthenticated unless GITHUB_TOKEN is set."""
    try:
        if sort_by not in SORTS:
            raise ValueError(f"sort_by must be one of {sorted(SORTS)}, got {sort_by!r}")
        search_query = query.strip()
        if not search_query:
            raise ValueError("query is required")
        if language.strip():
            search_query = f"{search_query} language:{language.strip()}"

        headers = {"Accept": "application/vnd.github+json", "User-Agent": "AI20k-Day04-Research-Agent/1.0"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"

        params: dict[str, Any] = {"q": search_query, "per_page": max(1, int(limit or 5))}
        if SORTS[sort_by]:
            params["sort"] = SORTS[sort_by]
            params["order"] = "desc"

        response = requests.get(API, params=params, headers=headers, timeout=TIMEOUT)
        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise RuntimeError("GitHub search rate limit reached (60/hour unauthenticated). Set GITHUB_TOKEN to raise it.")
        response.raise_for_status()
        data = response.json()
        return {
            "tool": "search_github_repos",
            "query": search_query,
            "sort_by": sort_by,
            "total_found": data.get("total_count"),
            "items": [_repo_item(repo) for repo in data.get("items", [])],
        }
    except Exception as exc:
        return err("search_github_repos", exc)
