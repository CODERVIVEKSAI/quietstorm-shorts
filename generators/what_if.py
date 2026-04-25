"""What If generator — hypothetical scenarios answered with surprising science/logic.
Randall Munroe / xkcd What-If vibe."""

import argparse
import json
from pathlib import Path
from generators.base import build

FORMAT = "what_if"


def _prompt() -> str:
    return """Pick ONE fun, surprising "What if..." hypothetical that's answerable with
real science or logic in under 45 seconds. Good examples:

- "What if you tried to reach the moon in a Tesla?"
- "What if everyone on Earth jumped at the same time?"
- "What if the sun disappeared for one second?"
- "What if you filled the ocean with Coca-Cola?"
- "What if gravity reversed for 5 seconds?"

Avoid: anything politically loaded, gruesome, or sexual.

Write a 50-70 word YouTube Short voiceover:
- Open with the "What if" question (hook)
- Spend 2-3 sentences building the scenario
- Deliver a surprising, real answer rooted in physics/biology/math
- End with a punchy beat (no CTA)

Return JSON:
- script: 50-70 word voiceover
- premise: the "What if..." question
- title: under 60 chars, starts with "What if"
- hashtags: 5-8 with #
- visual_query: 2-3 word Pexels query matching the scenario
  (e.g., "moon space", "ocean waves", "lightning storm")
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
