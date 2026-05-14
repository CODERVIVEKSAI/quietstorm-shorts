"""Gemini-backed script generation. Returns structured JSON per format.

Uses the google-genai SDK (not the legacy google-generativeai package),
because only google-genai exposes the `google_search` tool that Gemini 2.x
models require for grounding. Tries gemini-2.5-flash-lite first (cheap,
fast), falls back to gemini-2.5-flash. Retries with backoff on rate-limit
errors so parallel matrix jobs don't all fail when they hit the per-minute
cap at the same time.
"""

import json
import os
import re
import time
import random

from google import genai
from google.genai import types as genai_types
from google.genai import errors as genai_errors

# Try the bigger model first for grounded prompts — flash-lite is cheap but
# noticeably less aggressive about calling the google_search tool, which leads
# to stale answers (the model just writes from training data instead of
# searching). flash-lite stays as the fallback if flash hits rate limits.
_MODEL_CANDIDATES = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set")
        _client = genai.Client(api_key=key)
    return _client


def _extract_json(text: str) -> dict:
    """Find a JSON object inside the model's reply.

    Gemini sometimes returns multiple ```json fenced blocks (one for the main
    script, one for the match_info, sometimes a 'reasoning' block). The old
    regex-based approach grabbed the first balanced `{...}` it saw, which was
    often the SMALLER match_info object — that's how the saved script.json
    ended up with just home_team/away_team/scores and no narration.

    Strategy: scan for every balanced `{...}` substring (depth-aware,
    string-aware), parse each one, and prefer the candidate that actually
    contains a "script" field. Falls back to the candidate with the most
    keys if none has "script".
    """
    text = text.strip()

    # Fast path: whole reply is valid JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    candidates: list[dict] = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        in_string = False
        escape = False
        for j in range(i, len(text)):
            c = text[j]
            if escape:
                escape = False
                continue
            if c == "\\" and in_string:
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[i : j + 1])
                        if isinstance(obj, dict):
                            candidates.append(obj)
                    except json.JSONDecodeError:
                        pass
                    break
        i = max(i + 1, j + 1) if depth == 0 else i + 1

    if not candidates:
        raise ValueError(f"No JSON object found in model output: {text[:300]}")

    # Prefer the candidate that has the narration — that's the "real" payload.
    with_script = [c for c in candidates if "script" in c]
    if with_script:
        return with_script[0]
    # Otherwise pick the biggest by key count, breaking ties by serialized length.
    candidates.sort(key=lambda d: (len(d), len(json.dumps(d, default=str))), reverse=True)
    return candidates[0]


def _retry_delay_from(err: Exception) -> float:
    """Gemini errors often include 'Please retry in NNs' — parse it if present."""
    m = re.search(r"retry in ([0-9.]+)s", str(err))
    if m:
        return min(70.0, float(m.group(1)) + 3)
    return 30.0


def _status_code(err: Exception) -> int | None:
    """Pull the HTTP-ish status out of a genai APIError, if present."""
    for attr in ("code", "status_code", "status"):
        v = getattr(err, attr, None)
        if isinstance(v, int):
            return v
    return None


def _grounding_sources(resp) -> list[dict]:
    """Pull real URLs out of the response's grounding_metadata. These are
    the search-result chunks Gemini was actually shown — unlike URLs the
    model writes into the JSON body, which it tends to hallucinate (e.g.
    invented goodreads.com/quotes/<id> pages that 404)."""
    out: list[dict] = []
    seen: set[str] = set()
    for cand in getattr(resp, "candidates", None) or []:
        gm = getattr(cand, "grounding_metadata", None)
        if not gm:
            continue
        for chunk in getattr(gm, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            if not web:
                continue
            uri = getattr(web, "uri", None)
            if not uri or uri in seen:
                continue
            seen.add(uri)
            title = (getattr(web, "title", None) or "").strip()
            out.append({"claim": title, "source": uri})
    return out


def _call(prompt: str, *, grounded: bool, label: str) -> dict:
    """Single Gemini call with retry + model fallback. `grounded=True` enables
    the Google Search tool so the model can look facts up before answering.
    When grounded, the response's grounding_metadata overrides any `sources`
    field the model wrote — model-written URLs hallucinate constantly."""
    client = _get_client()
    last_err: Exception | None = None
    for model_name in _MODEL_CANDIDATES:
        for attempt in range(2):
            try:
                config = None
                if grounded:
                    config = genai_types.GenerateContentConfig(
                        tools=[
                            genai_types.Tool(google_search=genai_types.GoogleSearch())
                        ]
                    )
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                parsed = _extract_json(resp.text)
                if grounded:
                    real = _grounding_sources(resp)
                    if real:
                        parsed["sources"] = real
                return parsed
            except genai_errors.ClientError as e:
                code = _status_code(e)
                if code == 429:
                    wait = min(45.0, _retry_delay_from(e) + random.uniform(0, 5))
                    print(f"[{label}] {model_name} rate-limited; waiting {wait:.0f}s "
                          f"(attempt {attempt + 1}/2)…")
                    last_err = e
                    time.sleep(wait)
                    continue
                last_err = e
                print(f"[{label}] {model_name} client error ({code}): {e}; "
                      "trying next model…")
                break
            except genai_errors.ServerError as e:
                last_err = e
                print(f"[{label}] {model_name} server error; retrying in 5s "
                      f"(attempt {attempt + 1}/2)…")
                time.sleep(5)
                continue
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
    """
    note = _GROUNDED_NOTES.get(format_name, _GROUNDED_NOTES["custom"])
    wrapped = f"""You have access to Google Search and MUST use it for this task. Issue
search queries BEFORE writing — your training data is stale and will produce
wrong dates, wrong scores, and made-up matches. Do not skip the tool because
you "think you remember" the event; the fact-checker will spot it.

Concretely: call google_search at least once (more if needed) to confirm the
specific event you're writing about happened in the requested time window
and that every named team / player / score / date in your script matches a
real search result. If your first query returns nothing recent, try a
different query — don't give up after one search.

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
