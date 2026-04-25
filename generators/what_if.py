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

- "What if you tried to walk to the moon"
- "What if everyone on Earth jumped at the same time"
- "What if the sun disappeared for one second"
- "What if you filled the ocean with Coca-Cola"
- "What if gravity reversed for 5 seconds"
- "What if you skipped a stone across the Pacific"

Avoid: anything politically loaded, gruesome, or sexual.
NEVER write stylized interjections like "ARRRGGHHHH", "OOOMG", "AAAAH",
"NOOOOO" — the TTS engine spells them out letter-by-letter. Use real words:
"Wow.", "Yep.", "Nope.", "What?!" etc.

TONE: Gen-Z / Gen-Alpha brainrot energy (16-22 yr old). Fast pacing, mid-sentence pivots,
self-aware. Sound like the curious kid in class, not a documentary narrator. It's okay to
sprinkle modern phrasing where it lands naturally ("low-key wild", "the math is mathing",
"that's diabolical", "fr fr", "and that's crazy because...", "POV:"). Lean absurdist.
NO try-hard slang dump. NO boomer "imagine if you will...". Don't force it — pick 0-2
phrases that fit, then write clean.

Write a 50-70 word YouTube Short voiceover:
- Open with the "What if" question (hook)
- Build the scenario in 1-2 sentences with personality
- Deliver a surprising, REAL answer rooted in physics/biology/math (numbers > vibes)
- End with a punchy beat — meta, savage, or quietly absurd

Return JSON:
- script: 50-70 word voiceover
- premise: the "What if..." question
- title: under 60 chars, starts with "What if" (lowercase is fine)
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
