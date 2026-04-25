"""Gemini-backed script generation. Returns structured JSON per format.

Tries gemini-2.5-flash-lite first (large free quota, ~1500 RPD), falls back to
gemini-2.5-flash on errors. Quota errors on the first model retry against the
second instead of failing the run.
"""

import json
import os
import re
import google.generativeai as genai
from google.api_core import exceptions as gax

# Try lite first — much higher free-tier quota. Flash is fallback for quality
# but is rate-limited to ~20 RPD on free tier so we use it only when lite fails.
_MODEL_CANDIDATES = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]

_configured = False


def _configure():
    global _configured
    if not _configured:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=key)
        _configured = True


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model output: {text[:200]}")
    return json.loads(text[start : end + 1])


def generate(prompt: str) -> dict:
    """Run a generation prompt. Tries each candidate model in order until one succeeds."""
    _configure()
    last_err = None
    for model_name in _MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt)
            return _extract_json(resp.text)
        except (gax.ResourceExhausted, gax.NotFound, gax.PermissionDenied) as e:
            print(f"[script] {model_name} unavailable ({type(e).__name__}); trying next…")
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("no Gemini model succeeded")


def edit(previous: dict, edit_instruction: str, format_hint: str) -> dict:
    """Take a previously-generated script and apply an edit instruction."""
    prompt = f"""You previously generated this {format_hint} script as JSON:

{json.dumps(previous, indent=2)}

Apply this edit instruction and return the REVISED script as the same JSON shape:

EDIT INSTRUCTION: {edit_instruction}

Return ONLY the revised JSON, no prose.
"""
    return generate(prompt)
