"""Gemini-backed script generation. Returns structured JSON per format.

Every generator calls `generate()` with a system prompt + user prompt.
`edit()` takes a previous script + an edit instruction and returns a revised script.
"""

import json
import os
import re
import google.generativeai as genai

_MODEL_NAME = "gemini-2.5-flash"  # free tier; swap to gemini-2.5-flash-lite if quota is tight

_client = None


def _model():
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=key)
        _client = genai.GenerativeModel(_MODEL_NAME)
    return _client


def _extract_json(text: str) -> dict:
    """Gemini sometimes wraps JSON in ```json ... ``` fences. Strip and parse."""
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
    """Run a generation prompt. Expects the model to return JSON."""
    resp = _model().generate_content(prompt)
    return _extract_json(resp.text)


def edit(previous: dict, edit_instruction: str, format_hint: str) -> dict:
    """Take a previously-generated script and apply an edit instruction."""
    prompt = f"""You previously generated this {format_hint} script as JSON:

{json.dumps(previous, indent=2)}

Apply this edit instruction and return the REVISED script as the same JSON shape:

EDIT INSTRUCTION: {edit_instruction}

Return ONLY the revised JSON, no prose.
"""
    return generate(prompt)
