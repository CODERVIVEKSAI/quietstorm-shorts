"""Gemini-backed script generation. Returns structured JSON per format.

Tries gemini-2.5-flash-lite first (large free quota, ~1500 RPD, 15 RPM), falls
back to gemini-2.5-flash. Retries with backoff on rate-limit errors so parallel
matrix jobs don't all fail when they hit the 15 RPM cap simultaneously.
"""

import json
import os
import re
import time
import random
import google.generativeai as genai
from google.api_core import exceptions as gax

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


def _retry_delay_from(err: Exception) -> float:
    """Gemini errors often include 'Please retry in NNs' — parse it if present."""
    m = re.search(r"retry in ([0-9.]+)s", str(err))
    if m:
        return min(70.0, float(m.group(1)) + 3)
    return 30.0


def generate(prompt: str) -> dict:
    """Generate one script. With matrix running serially we should rarely hit
    rate limits, so retry once with a short wait then move on."""
    _configure()
    last_err = None
    for model_name in _MODEL_CANDIDATES:
        for attempt in range(2):
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content(prompt)
                return _extract_json(resp.text)
            except gax.ResourceExhausted as e:
                last_err = e
                wait = min(45.0, _retry_delay_from(e) + random.uniform(0, 5))
                print(f"[script] {model_name} rate-limited; waiting {wait:.0f}s (attempt {attempt + 1}/2)…")
                time.sleep(wait)
                continue
            except (gax.NotFound, gax.PermissionDenied) as e:
                print(f"[script] {model_name} unusable ({type(e).__name__}); trying next model…")
                last_err = e
                break
    raise last_err if last_err else RuntimeError("no Gemini model succeeded")


def edit(previous: dict, edit_instruction: str, format_hint: str) -> dict:
    """Take a previously-generated script and apply an edit instruction."""
    from .style import WRITING_RULES
    prompt = f"""{WRITING_RULES}

You previously generated this {format_hint} script as JSON:

{json.dumps(previous, indent=2)}

Apply this edit instruction and return the REVISED script as the same JSON
shape, while honoring all the writing rules above:

EDIT INSTRUCTION: {edit_instruction}

Return ONLY the revised JSON, no prose.
"""
    return generate(prompt)
