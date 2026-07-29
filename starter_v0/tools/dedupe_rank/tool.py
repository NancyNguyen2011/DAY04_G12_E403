from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

from tools._shared import domain, err, terms


TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "ref", "ref_src", "s", "t")

AUTHORITY = {
    "arxiv.org": 5,
    "openai.com": 4,
    "anthropic.com": 4,
    "deepmind.google": 4,
    "research.google": 4,
    "nature.com": 4,
    "news.ycombinator.com": 3,
    "techcrunch.com": 3,
    "theverge.com": 3,
    "reuters.com": 3,
    "wired.com": 2,
    "vnexpress.net": 2,
}


def _canonical_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlparse(url.strip())
        query = "&".join(
            piece for piece in parts.query.split("&")
            if piece and not piece.split("=")[0].lower().startswith(TRACKING_PREFIXES)
        )
        path = parts.path.rstrip("/") or "/"
        return urlunparse((parts.scheme.lower(), parts.netloc.lower().replace("www.", ""), path, "", query, ""))
    except Exception:
        return url.strip()


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def _similar(a: str, b: str) -> bool:
    """Jaccard overlap on content words; catches the same story retitled per outlet."""
    ta, tb = terms(a), terms(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.7


def dedupe_and_rank(
    items: list[dict[str, Any]] | None = None,
    prefer: str = "authority",
    max_items: int = 10,
) -> dict[str, Any]:
    """Merge items gathered from several sources into one deduplicated, ranked list."""
    try:
        items = items or []
        kept: list[dict[str, Any]] = []
        duplicates: list[dict[str, str]] = []

        for item in items:
            url_key = _canonical_url(item.get("url", ""))
            title_key = _title_key(item.get("title", ""))
            match = None
            for existing in kept:
                if url_key and url_key == existing["_url_key"]:
                    match = existing
                    break
                if title_key and (title_key == existing["_title_key"] or _similar(title_key, existing["_title_key"])):
                    match = existing
                    break
            if match:
                match["_dup_count"] += 1
                sources = match.setdefault("also_seen_in", [])
                source = item.get("source") or domain(item.get("url", ""))
                if source and source not in sources and source != match.get("source"):
                    sources.append(source)
                duplicates.append({"title": item.get("title", ""), "merged_into": match.get("title", "")})
                continue
            entry = dict(item)
            entry["_url_key"] = url_key
            entry["_title_key"] = title_key
            entry["_dup_count"] = 1
            kept.append(entry)

        def score(entry: dict[str, Any]) -> tuple:
            source = entry.get("source") or domain(entry.get("url", ""))
            authority = AUTHORITY.get((source or "").lower().replace("www.", ""), 1)
            corroboration = entry["_dup_count"]
            date = str(entry.get("date") or "")
            if prefer == "recency":
                return (date, corroboration, authority)
            return (authority, corroboration, date)

        kept.sort(key=score, reverse=True)
        limit = max(1, int(max_items or 10))
        ranked = []
        for rank, entry in enumerate(kept[:limit], start=1):
            clean = {k: v for k, v in entry.items() if not k.startswith("_")}
            clean["rank"] = rank
            clean["corroborating_sources"] = entry["_dup_count"]
            ranked.append(clean)

        return {
            "tool": "dedupe_and_rank",
            "prefer": prefer,
            "input_count": len(items),
            "output_count": len(ranked),
            "removed_duplicates": len(duplicates),
            "duplicates": duplicates,
            "items": ranked,
        }
    except Exception as exc:
        return err("dedupe_and_rank", exc)
