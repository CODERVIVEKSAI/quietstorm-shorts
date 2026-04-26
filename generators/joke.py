"""Joke generator — clean, observational humor that lands in <25 seconds."""

import argparse
import json
from pathlib import Path
from generators.base import build

FORMAT = "joke"


def _prompt() -> str:
    return """Write a 75-90 word joke routine that lands in ~50 seconds as a YouTube Short.
Build a setup-with-tangent-then-payoff structure (NOT a one-liner). Mini-rant
energy works great here.

Rules:
- Audio-only humor — no puns that need to be SEEN
- Clean: not offensive, not political, not mean-spirited
- Setup + punchline. Setup under 2 sentences.

TONE: Gen-Z / Gen-Alpha humor. Observational, absurdist, self-aware. Hits the way
relatable TikTok jokes hit. Modern references okay (apps, online life, school, gym,
group chats, AI, parents who just discovered TikTok). Subtle slang okay if it lands
naturally ("the way that...", "low-key", "no because actually", "and that's so fr").
NOT cringe boomer dad jokes. NOT try-hard slang dumps. NOT skibidi-coded forced brainrot.

Examples of vibe (don't reuse):
- "Therapist: 'And what do we do when we feel anxious?' Me: 'Open Instagram, scroll until I dissociate, then forget what I was anxious about.' Therapist: 'You don't have insurance, do you.'"
- "Group chat at 3am: someone sends 'u up?'. I'm not. But now I am. And so is everyone else. We don't reply. We just lurk. This is friendship in 2026."

Return JSON:
- script: full voiceover (75-90 words, setup + tangent + payoff + tiny beat)
- setup: the setup line
- punchline: the punchline
- title: under 60 chars, hook without spoiling (lowercase is fine)
- hashtags: 5-8 with #
- visual_query: 2-3 word Pexels query for b-roll matching the joke's topic
  (e.g., "office workers", "phone scrolling", "coffee shop")
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
