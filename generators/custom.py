"""Custom generator — takes any free-form prompt and turns it into a Short.
Triggered via the custom.yml workflow (workflow_dispatch) with a `prompt` input."""

import argparse
import json
from pathlib import Path
from generators.base import build

FORMAT = "custom"


def _wrap(user_prompt: str) -> str:
    return f"""Write a YouTube Shorts voiceover script based on this topic/request:

USER REQUEST: {user_prompt}

Constraints:
- 40-70 words
- Clean, non-political, non-offensive
- Has a hook in the first 3 seconds
- Under 55 seconds when read aloud at natural pace

Return JSON:
- script: the voiceover
- title: under 60 chars, hook-y
- hashtags: 5-8 with #
- visual_query: 2-3 word Pexels search query
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--prompt", required=True, help="Free-form topic/request")
    parser.add_argument("--edit", default=None)
    parser.add_argument("--previous-script", default=None)
    args = parser.parse_args()

    previous = json.loads(Path(args.previous_script).read_text()) if args.previous_script else None
    prompt = _wrap(args.prompt) if not args.edit else ""

    out = build(FORMAT, prompt, args.run_id, edit_instruction=args.edit, previous_script=previous)
    print(f"Built {FORMAT} at {out}")


if __name__ == "__main__":
    main()
