"""Golden Lady ad generator. Rotates product focus daily so the channel doesn't
push the same item every day. Reads data/company.md for tone guidance."""

import argparse
import json
from datetime import date
from pathlib import Path
from lib.config import load_company
from generators.base import build

FORMAT = "golden_lady"

# Weekly rotation. Day-of-year modulo list length.
PRODUCT_ROTATION = [
    "hand-pounded turmeric powder",
    "cold-pressed sesame (gingelly) oil",
    "hand-pounded red chili powder",
    "cold-pressed coconut oil",
    "hand-pounded coriander powder",
    "cold-pressed groundnut oil",
    "hand-pounded cumin powder",
    "cold-pressed mustard oil",
    "hand-pounded black pepper",
    "hand-pounded garam masala",
]


def _today_product() -> str:
    return PRODUCT_ROTATION[date.today().toordinal() % len(PRODUCT_ROTATION)]


def _prompt() -> str:
    company = load_company()
    product = _today_product()
    return f"""You are writing a 30-second YouTube Short advertisement for Golden Lady.

Company brief:
---
{company}
---

TODAY'S PRODUCT FOCUS: {product}

Write a voiceover script of 45-60 words:
- Open with a relatable hook (a question, a kitchen moment, a small observation)
- Introduce the product naturally (not "BUY NOW")
- State ONE clear benefit (taste, health, tradition — pick one, don't list)
- Close with a soft CTA ("Link in bio" / "DM us" — pick one)

Tone: warm, trustworthy, like a family member sharing a tip. NOT salesy. NOT yelling.
No medical claims. Okay to reference tradition and home cooking.

Return JSON:
- script: 45-60 word voiceover
- product_focus: "{product}"
- title: under 60 chars, product-focused and curiosity-driven
- hashtags: 5-8 with # (include #goldenlady, #healthyliving, #shorts, + product-specific)
- visual_query: 2-3 word Pexels query
  (e.g., "indian spices kitchen", "cooking oil bottle", "mortar pestle spice")
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
