"""Single source of truth for TTS-friendly writing + viral Shorts conventions.

Injected into the top of EVERY generation and edit prompt by base.py / script.py.
Edit this one file to retune the entire channel's voice."""

WRITING_RULES = """\
=== HOW TO WRITE THIS SCRIPT ===

1. WRITE FOR SPEECH, NOT READING.
   - Spell out numbers: "ten thousand", not "10,000".
   - Spell out symbols: "percent" not "%", "and" not "&", "dollars" not "$".
   - No ALL CAPS words (they get spelled letter-by-letter).
   - No acronyms unless universally said as a word (NASA okay, FYI not).
   - No stylized interjections like "ARRRGGHHHH", "OOOMG", "AAAAH" — TTS spells
     them out. Use "Argh!", "OMG!", "Wow!" with punctuation.

2. CONVERSATIONAL, NOT FORMAL.
   - Direct address: say "you", not "one" or "people".
   - Contractions: "don't", "you're", "it's".
   - Hooks like: "you won't believe this", "here's the crazy part",
     "wait... what?", "okay but think about this", "no because actually".

3. SHORT SENTENCES. 5-10 WORDS EACH.
   Long compound sentences sound robotic when read aloud. Break them up.
   Periods are free.

4. PUNCTUATION CONTROLS PACING.
   - Commas where you'd breathe.
   - Ellipses (...) for thoughtful pauses, especially before a payoff.
   - Em-dashes (—) for sudden pivots.
   - Question marks make the voice rise. Use them.

   Good rhythm example:
       "This looks normal...
        but wait —
        something's wrong."

5. EMOTION CUES (engineered into the words):
   - Surprise: "wait... what?"
   - Suspense: "and then..."
   - Emphasis: "this changes everything."
   - Pivot: "but here's the thing —"

6. VIRAL-SHORTS CONVENTIONS:
   - HOOK IN THE FIRST 3 SECONDS. Lead with the most surprising fact, claim,
     or question. NEVER waste the opening on "today we'll talk about".
   - Pattern interrupts welcome — mid-sentence pivots keep retention high.
   - End with a payoff that pays back the hook. NOT a corporate CTA dump.
     "Like and subscribe" energy is dead.
   - Cliffhangers work: "...but the next part is wild."

7. OUTPUT FORMAT:
   The "script" field must be a single string of voiceover text only.
   No stage directions, no [pause] markers, no speaker labels, no SFX cues.
   Punctuation is your only stage direction.

8. B-ROLL VISUAL QUERIES — return MULTIPLE.
   In your JSON output, ALSO include a "visual_queries" field: an ORDERED
   list of 3-8 distinct 2-3-word Pexels stock-footage search queries, one
   per BEAT of your script. The list order must follow the script's flow:
       index 0  → hook / opening
       index 1  → setup
       middle   → main point, example, twist
       last     → closer / payoff
   Use 3 queries for slow/contemplative scripts (quote, ASMR), 5-6 for
   typical pacing, 7-8 for fast/dense scripts (jokes, sports recaps).
   Each query must be VISUALLY DIFFERENT from the others — do NOT return
   five variations of "person running" or "city night". Pick concrete
   nouns + actions that Pexels actually has footage of (e.g. "sunrise
   mountain", "coffee pouring", "office workers", "lightning storm").
   The old singular "visual_query" field is no longer used — return
   "visual_queries" instead.
"""
