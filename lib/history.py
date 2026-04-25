"""Generation history. Records every successful generation's title (or other
unique-ish identifier) per format so future generations don't repeat themselves.

Same JSONL pattern as edit_log: one entry per line, committed back to the
repo by the workflow."""

import json
from datetime import datetime, timezone
from pathlib import Path
from .config import DATA_DIR

LOG_PATH = DATA_DIR / "generation_log.jsonl"


def record(format_name: str, title: str, premise: str = "") -> None:
    """Append a single generation record to the log."""
    if not title.strip():
        return
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "format": format_name,
        "title": title.strip(),
        "premise": premise.strip(),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def recent(format_name: str, limit: int = 30) -> list[dict]:
    """Most recent entries for a format, newest first."""
    if not LOG_PATH.exists():
        return []
    entries: list[dict] = []
    for line in LOG_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("format") == format_name:
            entries.append(obj)
    return list(reversed(entries))[:limit]


def avoid_block(format_name: str, limit: int = 25) -> str:
    """A 'do not repeat these' section to splice into a generation prompt.
    Empty string if there's no history yet."""
    history = recent(format_name, limit)
    if not history:
        return ""
    lines = ["", "AVOID THESE — already covered recently, do NOT repeat (vary topic, premise, framing):"]
    for h in history:
        bullet = h["title"]
        if h.get("premise"):
            bullet = f"{h['title']} ({h['premise']})"
        lines.append(f"- {bullet}")
    return "\n".join(lines)
