"""Joke generator — clean, observational humor that lands in <25 seconds."""

import argparse
import json
from pathlib import Path
from generators.base import build

FORMAT = "joke"


def _prompt() -> str:
    return """Write ONE clean joke that lands in under 25 seconds as a YouTube Short.

Rules:
- Observational or absurd humor — NOT offensive, NOT political, NOT mean-spirited
- NOT a pun that relies on text (audio-only medium)
- Setup + punchline structure. Keep setup under 2 sentences.
- Works for a global audience

Bad: dad jokes that need you to SEE the pun
Good: "I told my plants I was leaving town. They said that's fine, they weren't
growing attached anyway." — observational, lands in audio.

Return JSON:
- script: full voiceover (30-45 words, setup + punchline + tiny beat)
- setup: the setup line
- punchline: the punchline
- title: under 60 chars, hints at topic without spoiling
- hashtags: 5-8 with #
- visual_query: 2-3 word Pexels query for b-roll matching the joke's topic
  (e.g., "office workers", "houseplants", "coffee shop")
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--edit", default=None)
    parser.add_argument("--previous-script", default=None)
    args = parser.parse_args()

    previous = json.loads(Path(args.previous_script).read_text()) if args.previous_script else None
    prompt = "" if args.edit else _prompt()

    out = build(FORMAT, prompt, args.run_id, edit_instruction=args.edit, previous_script=previous)
    print(f"Built {FORMAT} at {out}")


if __name__ == "__main__":
    main()
