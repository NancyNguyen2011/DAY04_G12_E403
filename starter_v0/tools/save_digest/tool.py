from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from tools._shared import ROOT, err


NOTES_DIR = ROOT / "notes"
MAX_CHARS = 100_000


def _safe_name(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", (title or "").strip()).strip("-").lower()
    slug = slug[:60] or "digest"
    return f"{datetime.now():%Y%m%d-%H%M%S}-{slug}.md"


def save_digest(markdown: str = "", title: str = "", confirmed: bool = False) -> dict[str, Any]:
    """Write a finished digest to notes/ as a markdown file. Requires explicit confirmation."""
    if not confirmed:
        return {
            "tool": "save_digest",
            "status": "needs_confirmation",
            "filename": _safe_name(title),
            "chars": len(markdown or ""),
            "message": "Only save after the user explicitly confirms.",
        }
    try:
        if not (markdown or "").strip():
            raise ValueError("Refusing to save an empty digest")
        if len(markdown) > MAX_CHARS:
            raise ValueError(f"Digest too large: {len(markdown)} chars (limit {MAX_CHARS})")

        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        path = NOTES_DIR / _safe_name(title)
        header = f"# {title}\n\n" if title and not markdown.lstrip().startswith("#") else ""
        path.write_text(header + markdown, encoding="utf-8")
        return {
            "tool": "save_digest",
            "status": "saved",
            "path": str(path.relative_to(ROOT)),
            "chars": len(header + markdown),
        }
    except Exception as exc:
        return err("save_digest", exc)
