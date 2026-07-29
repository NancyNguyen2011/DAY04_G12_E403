from __future__ import annotations

from typing import Any


def get_weather(location: str = "Hanoi") -> dict[str, Any]:
    return {
        "tool": "get_weather",
        "location": location,
        "temperature": "26°C",
        "condition": "Partly Cloudy",
        "humidity": "70%",
    }
