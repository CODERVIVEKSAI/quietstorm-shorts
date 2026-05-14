"""Render a human-readable summary of a generated script for the manual-
approval reviewer. Prints to stdout and, if $GITHUB_STEP_SUMMARY is set,
appends the same markdown there so it shows up on the workflow run page —
the reviewer can read what they're about to approve without downloading
the artifact.

Usage:
  python scripts/script_summary.py <output_dir>

<output_dir> should contain script.json (and optionally factcheck.json).
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _fmt_list(items) -> str:
    if not items:
        return "_(none)_"
    return "\n".join(f"- {item}" for item in items)


def render(out_dir: Path) -> str:
    script_path = out_dir / "script.json"
    if not script_path.exists():
        return f"**No script.json found at `{script_path}`.**"

    spec = json.loads(script_path.read_text())

    # Path is output/<run_id>/<format>; the directory name IS the format.
    fmt = out_dir.name

    title = (spec.get("title") or "").strip() or "_(no title)_"
    narration = (spec.get("script") or "").strip() or "_(empty script)_"
    quote = (spec.get("quote") or "").strip()
    premise = (spec.get("premise") or "").strip()
    match_info = spec.get("match_info") if isinstance(spec.get("match_info"), dict) else None
    emphasis = spec.get("emphasis_phrases") or []
    queries = spec.get("visual_queries") or []
    if not queries and spec.get("visual_query"):
        queries = [spec["visual_query"]]
    hashtags = spec.get("hashtags") or []

    lines: list[str] = []
    lines.append(f"## Script for review — `{fmt}`")
    lines.append("")
    lines.append("### Reviewer options")
    lines.append("- **Approve** — click Review deployments → Approve. Video gets built.")
    lines.append("- **Reject** — click Review deployments → Reject (no comment). Run aborts.")
    lines.append(
        f"- **Edit** — Reject with comment `edit {fmt}: <your changes>` "
        "(e.g. `edit " + fmt + ": make it shorter, drop the second paragraph`). "
        "A new Edit Video run kicks off automatically, regenerating the script "
        "with your instruction applied. Re-review the new run."
    )
    lines.append(
        "- **Do nothing** — after **30 minutes** with no action, the deployment "
        "auto-approves and the video builds. So inaction = approval."
    )
    lines.append("")
    lines.append("_The narration below is what you'll hear AND what gets burned in as on-screen captions._")
    lines.append("")
    lines.append(f"### Title (YouTube)\n{title}")
    if quote:
        lines.append(f"\n### Quote\n> {quote}")
    if premise:
        lines.append(f"\n### Premise\n{premise}")

    if match_info:
        lines.append("\n### Scoreboard intro (renders as the first 2.8s of the video)")
        ht = (match_info.get("home_team") or "").strip()
        at = (match_info.get("away_team") or "").strip()
        hs = str(match_info.get("home_score") or "").strip()
        as_ = str(match_info.get("away_score") or "").strip()
        comp = (match_info.get("competition") or "").strip()
        mdate = (match_info.get("match_date") or "").strip()
        if comp:
            lines.append(f"- **Competition:** {comp}")
        lines.append(f"- **Match:** {ht}  **{hs} — {as_}**  {at}")
        if mdate:
            lines.append(f"- **Date:** {mdate}")

    lines.append("\n### Narration / on-screen captions")
    lines.append("")
    lines.append("```")
    lines.append(narration)
    lines.append("```")

    if emphasis:
        lines.append("\n### TTS emphasis phrases")
        lines.append(_fmt_list(emphasis))

    lines.append("\n### B-roll search queries (Pexels)")
    lines.append(_fmt_list(queries))

    if hashtags:
        lines.append("\n### Hashtags")
        lines.append(" ".join(hashtags))

    fc_path = out_dir / "factcheck.json"
    if fc_path.exists():
        try:
            fc = json.loads(fc_path.read_text())
            sources = fc.get("sources") or []
            lines.append("\n### Fact-check sources")
            if not sources:
                lines.append("_(none cited)_")
            else:
                for s in sources:
                    claim = (s.get("claim") or "").strip()
                    url = (s.get("source") or "").strip()
                    if claim and url:
                        lines.append(f"- **{claim}** — {url}")
                    elif claim:
                        lines.append(f"- {claim}")
                    elif url:
                        lines.append(f"- {url}")
        except Exception as e:
            lines.append(f"\n### Fact-check sources\n_(failed to parse factcheck.json: {e})_")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", help="Directory containing script.json")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    md = render(out_dir)

    print(md)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
