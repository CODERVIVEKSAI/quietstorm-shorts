"""Quote of the Day generator.

Pulls from data/seed_quotes.txt first (tracks used quotes in a state file in output/)
and falls back to Gemini-generated quotes when the seed list is exhausted.
"""

import argparse
import json
from pathlib import Path
from lib.config import DATA_DIR
from generators.base import build

FORMAT = "quote"
# State lives in data/ so it can be committed back to the repo and survive
# across GitHub Actions runs (the workflow commits this file after each run).
STATE_FILE = DATA_DIR / "quote_state.json"


def _next_seed_quote() -> tuple[str, str] | None:
    """Return (quote, attribution) for the next unused seed quote, or None if exhausted."""
    lines = []
    for raw in (DATA_DIR / "seed_quotes.txt").read_text().splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)

    used = set()
    if STATE_FILE.exists():
        used = set(json.loads(STATE_FILE.read_text()).get("used", []))

    for q in lines:
        if q not in used:
            used.add(q)
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps({"used": sorted(used)}))
            if "—" in q:
                quote, attribution = q.rsplit("—", 1)
                return quote.strip(), attribution.strip()
            return q, ""
    return None


def _prompt_from_seed(quote: str, attribution: str) -> str:
    return f"""You are writing a 30-second YouTube Short delivering this quote:

QUOTE: "{quote}"
ATTRIBUTION: {attribution or "unknown"}

TONE: Gen-Z / Gen-Alpha viewer (16-25 yr old). Self-aware, fast-paced, modern internet
humor. Confident not preachy. Lightly absurd. NO cringe boomer phrasing ("hustle culture",
"grind set", "boss up"). NO overused dead slang ("yass slay", "queen energy"). It's okay to
use *contained* modern phrasing ("real ones know", "lowkey", "the way that...", "this is...
coded") if it lands naturally. Don't force it.

Write a voiceover script of 40-55 words:
- Open with a 3-5 word hook (NOT the quote itself) — punchy, slightly unexpected
- Deliver the quote clearly
- 1-2 sentences of reflection that hit DIFFERENT — meta, observational, or quietly savage
- End with a short beat, no CTA

Return JSON with keys:
- script: the voiceover text
- title: YouTube Shorts title, under 60 chars, hook-y (lowercase is fine, no clickbait)
- hashtags: list of 5-8 relevant hashtags (with #)
- visual_query: 2-3 word Pexels search query for stock footage that fits the quote's mood
  (e.g., "sunrise mountain", "person running", "city night")
"""


def _prompt_fallback() -> str:
    return """Pick ONE original or classic quote (under 20 words). Modern wisdom > musty quotes.

TONE: Gen-Z / Gen-Alpha (16-25 yr old). Self-aware, fast-paced, modern internet humor.
Confident not preachy. NO cringe ("hustle culture", "grind set"). NO dead slang.

Structure: 3-5 word hook → quote → reflection that hits different → short beat.

Return JSON with keys:
- script: 40-55 word voiceover
- quote: the quote itself
- title: under 60 chars (lowercase is fine)
- hashtags: 5-8 hashtags with #
- visual_query: 2-3 word Pexels search query
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--edit", default=None, help="Edit instruction; regenerates from previous script")
    parser.add_argument("--previous-script", default=None, help="Path to previous script.json")
    args = parser.parse_args()

    previous = None
    if args.previous_script:
        previous = json.loads(Path(args.previous_script).read_text())

    if args.edit:
        prompt = ""  # ignored when editing
    else:
        seed = _next_seed_quote()
        if seed:
            prompt = _prompt_from_seed(*seed)
        else:
            prompt = _prompt_fallback()

    out = build(FORMAT, prompt, args.run_id, edit_instruction=args.edit, previous_script=previous)
    print(f"Built {FORMAT} at {out}")


if __name__ == "__main__":
    main()
