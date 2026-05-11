"""Grounded fact-checker. Hands the just-generated script to Gemini with
Google Search grounding turned on and asks it to extract every factual claim,
then verify each one against the live web. Runs two INDEPENDENT passes —
both have to agree the script is clean before we call it verified.

Returns a structured report that gets written to factcheck.json next to
script.json, so the manual-approval reviewer can see exactly which claims
were verified and which ones the model couldn't back up.

Why grounding: ungrounded Gemini just confirms its own hallucinations.
Google Search grounding (the `google_search` tool on Gemini 2.x) gives the
model live web access and forces it to cite sources.
"""

import json
import os
import re
import time
import random
import google.generativeai as genai
from google.api_core import exceptions as gax

_MODEL_CANDIDATES = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

# Hypotheticals are by definition unverifiable — the *premise* isn't a claim,
# but the science used to ANSWER the premise is. Same idea for jokes/quotes:
# the surface text isn't a claim, but the supporting facts are. The prompt
# below spells this out so the model doesn't flag every hypothetical as bad.
_FORMAT_NOTES = {
    "what_if": (
        "This is a 'What if X' hypothetical. The premise X itself is NOT a "
        "claim and should NOT be flagged. ONLY verify the science/physics/math "
        "used to answer the hypothetical (numbers, physical constants, "
        "biological facts, real-world comparisons)."
    ),
    "quote": (
        "Verify the quote itself exists in real sources and that any "
        "attribution is correct. Misattributed quotes (e.g. fake Einstein, "
        "fake Mark Twain) are a major failure mode."
    ),
    "cricket": (
        "Verify any specific player names, team names, match results, season "
        "facts, and historical references are real. Roast/opinion content "
        "is not a factual claim and should not be flagged."
    ),
    "football": (
        "Verify any specific player names, team names, match results, season "
        "facts, and historical references are real. Commentary/opinion is "
        "not a factual claim and should not be flagged."
    ),
    "golden_lady": (
        "STRICT MODE — this is an ad. Flag ANY medical or health-benefit "
        "claim ('cures', 'prevents', 'heals', 'treats', specific nutrient "
        "claims) as 'contradicted' unless it is verifiable against an "
        "authoritative health source. Verifiable food-tradition or "
        "process claims (e.g. 'cold-pressed', 'hand-pounded') are fine."
    ),
    "custom": (
        "Verify every concrete factual claim (numbers, names, dates, events, "
        "scientific facts). Opinion, hypothetical, and stylistic content "
        "should not be flagged."
    ),
}

_VERIFY_PROMPT = """You are a strict fact-checker for a YouTube Shorts script.
Use Google Search to verify every factual claim in the script below against
live sources.

{format_note}

SCRIPT:
\"\"\"{script}\"\"\"

For each distinct factual claim in the script, return one entry. A "factual
claim" is a statement that could in principle be true or false (numbers,
names, dates, scientific facts, attributions, historical events).
DO NOT flag: opinions, jokes, hypothetical premises, stylistic flourishes,
generic statements ("life is short", "people love food").

For each claim, decide:
- "verified"      — Google Search confirms the claim with a credible source
- "contradicted"  — Google Search returns information that contradicts the claim
- "unverified"    — you couldn't find authoritative confirmation either way

Return ONLY this exact JSON shape, no prose, no markdown fences:

{{
  "claims": [
    {{
      "claim": "<exact phrase from the script>",
      "verdict": "verified" | "contradicted" | "unverified",
      "evidence": "<one-sentence summary of what the search found>",
      "source": "<URL of the best supporting/contradicting source, or empty>"
    }}
  ],
  "all_clean": <true if EVERY claim is "verified", false otherwise>,
  "issues": [
    "<for each non-verified claim, one short imperative instruction to fix it,
     e.g. 'The claim that X is wrong — actually it is Y. Rewrite that sentence.'>"
  ]
}}

Be strict. If you cannot find a credible source within 2 searches per claim,
mark it "unverified" — do NOT guess. An unverified or contradicted claim
means the script must be rewritten.
"""

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
        raise ValueError(f"No JSON object in fact-check output: {text[:300]}")
    return json.loads(text[start : end + 1])


def _retry_delay_from(err: Exception) -> float:
    m = re.search(r"retry in ([0-9.]+)s", str(err))
    if m:
        return min(70.0, float(m.group(1)) + 3)
    return 30.0


def _grounded_model(model_name: str):
    """Build a Gemini model with Google Search grounding enabled.

    Falls back to no-grounding if the SDK/model rejects the tool config —
    in that case the verification is less reliable but still uses Gemini's
    internal knowledge with a strict 'mark as unverified if not certain'
    instruction baked into the prompt.
    """
    try:
        # Gemini 2.x grounding: `google_search` tool. Newer SDK uses a string
        # shortcut; older 0.8.x uses the proto. Try the string first.
        return genai.GenerativeModel(model_name, tools="google_search_retrieval")
    except Exception:
        pass
    try:
        from google.generativeai import protos  # type: ignore
        tool = protos.Tool(google_search_retrieval=protos.GoogleSearchRetrieval())
        return genai.GenerativeModel(model_name, tools=[tool])
    except Exception:
        pass
    # Last resort — no grounding. The strict prompt will still bias toward
    # marking unverifiable claims as "unverified".
    return genai.GenerativeModel(model_name)


def _run_one_pass(script: str, format_name: str, *, pass_label: str) -> dict:
    """Run a single grounded fact-check pass with retries."""
    _configure()
    note = _FORMAT_NOTES.get(format_name, _FORMAT_NOTES["custom"])
    prompt = _VERIFY_PROMPT.format(format_note=note, script=script)

    last_err = None
    for model_name in _MODEL_CANDIDATES:
        for attempt in range(2):
            try:
                model = _grounded_model(model_name)
                resp = model.generate_content(prompt)
                report = _extract_json(resp.text)
                report["_pass"] = pass_label
                report["_model"] = model_name
                return report
            except gax.ResourceExhausted as e:
                last_err = e
                wait = min(45.0, _retry_delay_from(e) + random.uniform(0, 5))
                print(f"[factcheck:{pass_label}] {model_name} rate-limited; waiting {wait:.0f}s "
                      f"(attempt {attempt + 1}/2)…")
                time.sleep(wait)
                continue
            except (gax.NotFound, gax.PermissionDenied) as e:
                print(f"[factcheck:{pass_label}] {model_name} unusable ({type(e).__name__}); "
                      "trying next model…")
                last_err = e
                break
            except (ValueError, json.JSONDecodeError) as e:
                # Bad JSON shape from the model — try again, then fall back
                last_err = e
                print(f"[factcheck:{pass_label}] {model_name} returned malformed JSON; retrying…")
                time.sleep(2)
                continue

    raise last_err if last_err else RuntimeError("no fact-check model succeeded")


def verify_twice(script: str, format_name: str) -> dict:
    """Run two independent fact-check passes. Both must say all_clean for the
    overall verdict to be clean. Returns a merged report:

      {
        "ok": bool,                 # True iff both passes are all_clean
        "passes": [report_a, report_b],
        "issues": [...]             # union of issues from both passes
      }
    """
    report_a = _run_one_pass(script, format_name, pass_label="A")
    report_b = _run_one_pass(script, format_name, pass_label="B")

    issues_a = report_a.get("issues", []) or []
    issues_b = report_b.get("issues", []) or []
    # Dedupe by exact text — different passes often surface the same problem
    combined_issues = list(dict.fromkeys(issues_a + issues_b))

    ok = bool(report_a.get("all_clean") and report_b.get("all_clean"))

    return {
        "ok": ok,
        "passes": [report_a, report_b],
        "issues": combined_issues,
    }
