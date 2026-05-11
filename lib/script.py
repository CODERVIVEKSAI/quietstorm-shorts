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


def _build_grounded_model(model_name: str):
    """Build a Gemini model with Google Search grounding enabled. Tries the
    Gemini 2.x `google_search` tool first (via several SDK paths because the
    0.8.x google-generativeai SDK exposes it inconsistently), then falls back
    to the 1.5-era `google_search_retrieval` string shortcut. Returns None if
    no grounding option is available — caller falls back to plain generation."""
    # Path A — gapic library directly (most reliable in 0.8.x)
    try:
        import google.ai.generativelanguage_v1beta as glm  # type: ignore
        if hasattr(glm, "GoogleSearch") and hasattr(glm, "Tool"):
            tool = glm.Tool(google_search=glm.GoogleSearch())
            return genai.GenerativeModel(model_name, tools=[tool])
    except Exception as e:
        print(f"[grounded] glm google_search failed: {e}")

    # Path B — genai.protos
    try:
        from google.generativeai import protos  # type: ignore
        if hasattr(protos, "GoogleSearch"):
            tool = protos.Tool(google_search=protos.GoogleSearch())
            return genai.GenerativeModel(model_name, tools=[tool])
    except Exception as e:
        print(f"[grounded] protos google_search failed: {e}")

    # Path C — dict form
    try:
        return genai.GenerativeModel(model_name, tools=[{"google_search": {}}])
    except Exception as e:
        print(f"[grounded] dict google_search failed: {e}")

    # Path D — old 1.5 tool (works only for 1.5 models; 2.x will reject at request time)
    try:
        return genai.GenerativeModel(model_name, tools="google_search_retrieval")
    except Exception as e:
        print(f"[grounded] google_search_retrieval string failed: {e}")

    print("[grounded] no grounding tool available; falling back to non-grounded generation")
    return None


def _is_grounding_unsupported_error(err: Exception) -> bool:
    msg = str(err).lower()
    return (
        "google_search" in msg
        or "tool" in msg and "not supported" in msg
    )


def _call(prompt: str, *, grounded: bool, label: str) -> dict:
    """Single Gemini call with retry + model fallback. `grounded=True` asks
    the SDK to enable Google Search grounding; if the API rejects the
    grounding tool at request time, we retry the SAME prompt without
    grounding rather than failing the whole script job."""
    _configure()
    last_err = None
    for model_name in _MODEL_CANDIDATES:
        for attempt in range(2):
            grounded_attempt = grounded
            try:
                if grounded_attempt:
                    model = _build_grounded_model(model_name)
                    if model is None:
                        grounded_attempt = False
                        model = genai.GenerativeModel(model_name)
                else:
                    model = genai.GenerativeModel(model_name)
                resp = model.generate_content(prompt)
                return _extract_json(resp.text)
            except gax.InvalidArgument as e:
                # Most common case: API rejected the grounding tool for this
                # model. Recover by retrying the same call non-grounded.
                if grounded_attempt and _is_grounding_unsupported_error(e):
                    print(f"[{label}] {model_name} rejected grounding tool ({e}); "
                          "retrying non-grounded on same model")
                    try:
                        model = genai.GenerativeModel(model_name)
                        resp = model.generate_content(prompt)
                        return _extract_json(resp.text)
                    except Exception as inner:
                        last_err = inner
                        # fall through to next attempt / next model
                else:
                    last_err = e
                    print(f"[{label}] {model_name} invalid argument ({e}); trying next model…")
                    break
            except gax.ResourceExhausted as e:
                last_err = e
                wait = min(45.0, _retry_delay_from(e) + random.uniform(0, 5))
                print(f"[{label}] {model_name} rate-limited; waiting {wait:.0f}s "
                      f"(attempt {attempt + 1}/2)…")
                time.sleep(wait)
                continue
            except (gax.NotFound, gax.PermissionDenied) as e:
                print(f"[{label}] {model_name} unusable ({type(e).__name__}); "
                      "trying next model…")
                last_err = e
                break
            except (ValueError, json.JSONDecodeError) as e:
                last_err = e
                print(f"[{label}] {model_name} returned malformed JSON; retrying…")
                time.sleep(2)
                continue
    raise last_err if last_err else RuntimeError("no Gemini model succeeded")


def generate(prompt: str) -> dict:
    """Plain Gemini generation (no grounding). Used for `joke` only — jokes
    are deliberately absurd so web grounding is a category error."""
    return _call(prompt, grounded=False, label="script")


# Per-format guidance for the grounded research-then-write call. Tells the
# model what counts as a "factual claim" vs. legitimate creative content for
# each format, so it doesn't try to fact-check a hypothetical or an opinion.
_GROUNDED_NOTES = {
    "what_if": (
        "The 'what if X' premise itself is hypothetical and does NOT need "
        "verification. EVERY piece of physics, biology, math, or real-world "
        "comparison you use to ANSWER the hypothetical MUST be grounded in "
        "search results before you write it. If you can't find a source "
        "for a number or fact, don't use that number — pick something you can "
        "verify, or phrase it vaguely."
    ),
    "quote": (
        "Search to verify the quote actually exists in the form you're using "
        "and that its attribution is correct. Misattributed quotes (fake "
        "Einstein, fake Twain, fake Buddha) are the #1 failure here. If you "
        "cannot find a reliable source attributing the quote to the named "
        "person, either correct the attribution or use a different quote."
    ),
    "cricket": (
        "Any specific player names, team names, match results, season facts, "
        "and historical references MUST be verified via search before you use "
        "them. Roast/opinion/banter content is free — fact-check only the "
        "concrete factual claims."
    ),
    "football": (
        "Any specific player names, team names, match results, season facts, "
        "and historical references MUST be verified via search before you use "
        "them. Commentary/opinion content is free — fact-check only the "
        "concrete factual claims."
    ),
    "golden_lady": (
        "STRICT MODE — this is an ad. ZERO medical/health-benefit claims "
        "unless you can verify them against an authoritative health source "
        "(WHO, NIH, peer-reviewed paper). Verifiable food-tradition or "
        "process claims (cold-pressed, hand-pounded, sourced from X region) "
        "are fine if you can find a real source describing the practice."
    ),
    "custom": (
        "Verify every concrete factual claim — numbers, names, dates, events, "
        "scientific facts — via search before you write it. Opinions, "
        "hypotheticals, and stylistic flourishes don't need verification."
    ),
}


def generate_grounded(base_prompt: str, format_name: str) -> dict:
    """Single Gemini call that does research + write + cite in one shot.
    Google Search grounding is enabled, so the model can look facts up
    BEFORE writing the script. The response includes a `sources` field
    listing every factual claim and where it came from — that's what we
    save to factcheck.json for the manual-approval reviewer.

    Replaces the older multi-call verify→revise loop. One API call instead
    of up to 16 per script.
    """
    note = _GROUNDED_NOTES.get(format_name, _GROUNDED_NOTES["custom"])
    wrapped = f"""You have access to Google Search. Use it BEFORE writing — research the
topic, verify every factual claim against real sources, then write the script
using ONLY facts you've verified.

FACT-CHECK RULES FOR THIS FORMAT ({format_name}):
{note}

If you cannot verify a specific number, name, date, or fact within 2-3 search
queries, REPLACE it with something you can verify (vaguer phrasing, a
different example) rather than guessing. It is much better to be vague and
right than specific and wrong.

In addition to the keys requested below, ALSO include in your JSON output a
"sources" field — a list of objects like:
  {{ "claim": "<exact phrase from your script>",
     "source": "<URL of the page that verified this claim>" }}
One entry per concrete factual claim you made. Opinions and hypotheticals
don't need a source.

ORIGINAL TASK:
{base_prompt}

Return ONLY the JSON object, no prose, no markdown fences. Make sure the
JSON is well-formed and parseable.
"""
    return _call(wrapped, grounded=True, label="grounded")


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


