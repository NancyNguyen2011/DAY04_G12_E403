from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests

from tools._shared import TIMEOUT, err


def _agent() -> str:
    return os.getenv("ARXIV_USER_AGENT", "AI20k-Day04-Research-Agent/1.0 (educational lab)")


def _summary(lang: str, title: str) -> dict[str, Any] | None:
    response = requests.get(
        f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title, safe='')}",
        headers={"User-Agent": _agent()},
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        return None
    data = response.json()
    if data.get("type") == "disambiguation":
        return None
    return {
        "title": data.get("title"),
        "url": (data.get("content_urls") or {}).get("desktop", {}).get("page", ""),
        "source": f"{lang}.wikipedia.org",
        "summary": data.get("extract") or "",
        "description": data.get("description"),
    }


def wiki_lookup(query: str = "", lang: str = "vi", limit: int = 1) -> dict[str, Any]:
    """Resolve a concept to Wikipedia summaries. Falls back en <-> vi when a page is missing."""
    try:
        lang = (lang or "vi").strip().lower()
        search = requests.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": max(1, int(limit or 1)),
                "format": "json",
            },
            headers={"User-Agent": _agent()},
            timeout=TIMEOUT,
        )
        search.raise_for_status()
        titles = [hit["title"] for hit in search.json().get("query", {}).get("search", [])]

        fallback_lang = "en" if lang != "en" else "vi"
        if not titles:
            lang, fallback_lang = fallback_lang, lang
            search = requests.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": query, "srlimit": 1, "format": "json"},
                headers={"User-Agent": _agent()},
                timeout=TIMEOUT,
            )
            search.raise_for_status()
            titles = [hit["title"] for hit in search.json().get("query", {}).get("search", [])]

        items: list[dict[str, Any]] = []
        for title in titles[: max(1, int(limit or 1))]:
            item = _summary(lang, title) or _summary(fallback_lang, title)
            if item:
                items.append(item)

        return {"tool": "wiki_lookup", "query": query, "lang": lang, "items": items}
    except Exception as exc:
        return err("wiki_lookup", exc)
