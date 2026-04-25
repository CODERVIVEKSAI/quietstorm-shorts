"""Edit-pattern memory. After every successful edit, append the user's
instruction to data/edit_log.jsonl. Future generations read the recent
patterns for each format and bias new scripts accordingly.

Format of edit_log.jsonl (one JSON per line):
    {"timestamp": "2026-04-25T09:23:33Z", "format": "joke", "instruction": "..."}
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from .config import DATA_DIR

LOG_PATH = DATA_DIR / "edit_log.jsonl"


def record_edit(format_name: str, instruction: str) -> None:
    """Append one edit to the log. Safe to call from CI."""
    if not instruction.strip():
        return
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "format": format_name,
        "instruction": instruction.strip(),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_recent_edits(format_name: str, limit: int = 10) -> list[dict]:
    """Return the most recent edits for a given format (newest first)."""
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


def preferences_block(format_name: str, limit: int = 10) -> str:
    """Build a 'USER PREFERENCES' section to splice into a generation prompt.
    Returns empty string if there are no recorded edits for this format."""
    edits = load_recent_edits(format_name, limit)
    if not edits:
        return ""
    lines = [
        "",
        "USER PREFERENCES — derived from your past edits to this format:",
    ]
    for e in edits:
        lines.append(f"- {e['instruction']}")
    lines.append(
        "Apply these preferences silently while keeping the format's structure. "
        "Don't mention 'preferences' in the script."
    )
    return "\n".join(lines)
