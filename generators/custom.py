"""Custom generator — takes a free-form prompt plus optional tone/length/visual/voice
overrides, and turns it into a Short. Triggered via the custom.yml workflow."""

import argparse
import json
from pathlib import Path
from generators.base import build

FORMAT = "custom"

# Tone presets baked into the script prompt
TONES = {
    "auto": "Pick the tone that best fits the topic.",
    "serious": "Tone: serious, calm, documentary-style. Authoritative not preachy.",
    "funny": "Tone: observational humor, self-aware, light. Punchline at the end.",
    "hype": "Tone: high-energy Gen-Z hype. Fast pacing, mid-sentence pivots, low-key/no-cap-style modern phrasing where it lands.",
    "chill": "Tone: laid-back, conversational, slightly philosophical. ASMR-friendly pacing.",
    "educational": "Tone: clear, curious, fact-driven. Numbers and real evidence over vibes.",
}

# Length presets in word counts and target seconds
LENGTHS = {
    "short": ("25-35 words", "20 seconds"),
    "medium": ("45-60 words", "35-45 seconds"),
    "max": ("75-95 words", "55-58 seconds"),
}

# Visual style hints fed to the Gemini prompt's visual_query field
VISUAL_HINTS = {
    "auto": "Pick a Pexels query that fits the topic naturally.",
    "people": "Visual query MUST favor footage with people doing things.",
    "no-people": "Visual query MUST avoid people. Use objects, places, abstract motion, nature.",
    "nature": "Visual query MUST be nature/landscape: forests, oceans, mountains, sky, weather.",
    "tech": "Visual query MUST be tech/urban: screens, code, city lights, devices, gadgets.",
    "abstract": "Visual query MUST be abstract: light leaks, particles, ink in water, smoke, slow motion.",
    "animation": "Visual query MUST be animated/cartoon/motion-graphics. Prefix with 'animated' or '3d animation' or 'motion graphics' or 'cartoon'. NO live-action people or photos.",
}

# Mood — overall feeling of the video. Shapes both script atmosphere and Pexels query.
MOODS = {
    "auto": "Pick a mood that fits the topic.",
    "uplifting": "Mood: uplifting, warm, inspiring. Golden-hour visuals, hopeful pacing, ending lands on a positive note.",
    "mysterious": "Mood: mysterious, intriguing. Slow reveals, low-key visuals, withhold the answer until the end. Suspenseful pacing.",
    "energetic": "Mood: high-octane and hype. Fast pacing, punchy delivery, restless visuals (city lights, action, motion).",
    "calm": "Mood: peaceful and meditative. Soft visuals, unhurried delivery, ASMR-friendly pacing, ending on stillness.",
    "dark": "Mood: dramatic and intense. High-contrast visuals, night/storm/shadow imagery, gravitas in delivery (no melodrama).",
    "nostalgic": "Mood: warm and retro. Faded visuals, sun-drenched memory aesthetic, bittersweet tone.",
}

# Voice ID overrides (matches edge-tts voice names)
VOICE_OVERRIDES = {
    "auto": None,  # use channel default
    "andrew": "en-US-AndrewMultilingualNeural",
    "brian": "en-US-BrianMultilingualNeural",
    "christopher": "en-US-ChristopherNeural",
    "prabhat": "en-IN-PrabhatNeural",
    "neerja": "en-IN-NeerjaNeural",
}


def _wrap(user_prompt: str, tone: str, length: str, visual: str, mood: str) -> str:
    tone_line = TONES.get(tone, TONES["auto"])
    word_count, secs = LENGTHS.get(length, LENGTHS["medium"])
    visual_line = VISUAL_HINTS.get(visual, VISUAL_HINTS["auto"])
    mood_line = MOODS.get(mood, MOODS["auto"])
    return f"""Write a YouTube Shorts voiceover script based on this topic/request:

USER REQUEST: {user_prompt}

{tone_line}

{mood_line}

Length target: {word_count} ({secs} when read aloud at natural pace).
Clean, non-political, non-offensive. Hook in the first 3 seconds.

{visual_line}

Return JSON with these exact keys:
- script: the voiceover text
- title: under 60 chars, hook-y (lowercase is fine)
- hashtags: list of 5-8 hashtags with #
- visual_query: 2-3 word Pexels search query (follow the visual style + mood rules above)
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--prompt", required=True, help="Free-form topic/request")
    parser.add_argument("--tone", default="auto", choices=list(TONES.keys()))
    parser.add_argument("--length", default="medium", choices=list(LENGTHS.keys()))
    parser.add_argument("--visual-style", default="auto", choices=list(VISUAL_HINTS.keys()))
    parser.add_argument("--mood", default="auto", choices=list(MOODS.keys()))
    parser.add_argument("--voice", default="auto", choices=list(VOICE_OVERRIDES.keys()))
    parser.add_argument("--edit", default=None)
    parser.add_argument("--previous-script", default=None)
    args = parser.parse_args()

    previous = json.loads(Path(args.previous_script).read_text()) if args.previous_script else None
    if args.edit:
        prompt = ""
    else:
        prompt = _wrap(args.prompt, args.tone, args.length, args.visual_style, args.mood)

    voice_override = VOICE_OVERRIDES.get(args.voice)

    out = build(
        FORMAT, prompt, args.run_id,
        edit_instruction=args.edit, previous_script=previous,
        voice_override=voice_override,
    )
    print(f"Built {FORMAT} at {out}")


if __name__ == "__main__":
    main()
