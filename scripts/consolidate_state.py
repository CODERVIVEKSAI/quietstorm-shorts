"""Run after the daily matrix completes. Reads each artifact directory under
artifacts/, extracts metadata.json + quote_state.json, and updates the
repo's data/generation_log.jsonl + data/quote_state.json so they persist
between runs.

Expects artifacts already downloaded into ./artifacts/<artifact-name>/...
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_ROOT = Path("artifacts")
GEN_LOG = ROOT / "data" / "generation_log.jsonl"
QUOTE_STATE = ROOT / "data" / "quote_state.json"


def main():
    if not ARTIFACTS_ROOT.exists():
        print(f"no artifacts dir at {ARTIFACTS_ROOT}, nothing to do")
        return 0

    new_entries = []
    for fmt_dir in sorted(ARTIFACTS_ROOT.iterdir()):
        if not fmt_dir.is_dir():
            continue
        meta_files = list(fmt_dir.rglob("metadata.json"))
        for meta_path in meta_files:
            try:
                meta = json.loads(meta_path.read_text())
            except Exception as e:
                print(f"skip {meta_path}: {e}")
                continue
            title = (meta.get("title") or "").strip()
            if not title:
                continue
            # Prefer a script-level field for premise; fall back to title only
            script_path = meta_path.parent / "script.json"
            premise = ""
            if script_path.exists():
                try:
                    spec = json.loads(script_path.read_text())
                    premise = (spec.get("premise") or spec.get("quote") or "").strip()
                except Exception:
                    pass
            new_entries.append({
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "format": meta.get("format", "unknown"),
                "title": title,
                "premise": premise,
            })

        # If this artifact carried a quote_state.json, replace the repo's copy
        qs = list(fmt_dir.rglob("quote_state.json"))
        if qs:
            QUOTE_STATE.parent.mkdir(parents=True, exist_ok=True)
            QUOTE_STATE.write_text(qs[0].read_text())
            print(f"updated quote_state from {qs[0]}")

    if new_entries:
        GEN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(GEN_LOG, "a") as f:
            for e in new_entries:
                f.write(json.dumps(e) + "\n")
        print(f"appended {len(new_entries)} entries to {GEN_LOG}")
    else:
        print("no new entries to append")

    return 0


if __name__ == "__main__":
    sys.exit(main())
