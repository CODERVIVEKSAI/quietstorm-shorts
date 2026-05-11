"""Shared build pipeline for every format: script -> tts -> visuals -> assemble."""

import json
from pathlib import Path
from lib import script as script_lib
from lib import tts, visuals, assemble
from lib.config import load_channel, voice_for, rate_for, OUTPUT_DIR
from lib.preferences import preferences_block
from lib.style import WRITING_RULES
from lib import history

# Formats that get grounded (research-via-Google-Search) generation instead
# of plain generation. The grounded call is one API request — the model
# searches, verifies, and writes in a single shot, citing each factual claim
# in a `sources` field in the response. Jokes are deliberately absurd so they
# skip grounding — verifying "what if everyone in the group chat went silent"
# is a category error.
GROUNDED_FORMATS = {"what_if", "quote", "cricket", "football", "golden_lady", "custom"}

# Per-format transition style for the video assembler. Punchy formats (jokes,
# sports recaps) get hard cuts so they hit on the beat; everything else gets
# a soft crossfade. New formats default to crossfade.
TRANSITION_BY_FORMAT = {
    "joke": "cut",
    "cricket": "cut",
    "football": "cut",
    "quote": "crossfade",
    "what_if": "crossfade",
    "golden_lady": "crossfade",
    "custom": "crossfade",
}


def build(format_name: str, prompt: str, run_id: str, edit_instruction: str | None = None,
          previous_script: dict | None = None, voice_override: str | None = None,
          stage: str = "all") -> Path:
    """Run the pipeline for one video. Returns the path to the output directory.

    `stage` selects which phases run:
      - "all"    — full pipeline (script -> tts -> visuals -> assemble)
      - "script" — only step 1 (writes script.json, then returns)
      - "video"  — skip step 1; load existing script.json from out_dir, then run 2-6.
                   Used by the two-stage GitHub workflows that gate audio/video on
                   manual approval after the script is generated.
    """
    if stage not in ("all", "script", "video"):
        raise ValueError(f"unknown stage: {stage!r}")

    out_dir = OUTPUT_DIR / run_id / format_name
    out_dir.mkdir(parents=True, exist_ok=True)
    script_path = out_dir / "script.json"

    if stage in ("all", "script"):
        # 1. Script — every prompt gets the channel-wide writing rules,
        # the "avoid these recent topics" history, and any learned preferences.
        if edit_instruction and previous_script:
            spec = script_lib.edit(previous_script, edit_instruction, format_name)
        else:
            full_prompt = WRITING_RULES + "\n" + prompt.rstrip()
            avoid = history.avoid_block(format_name)
            if avoid:
                full_prompt += "\n" + avoid
            prefs = preferences_block(format_name)
            if prefs:
                full_prompt += "\n" + prefs
            # Grounded one-shot for fact-heavy formats: Gemini researches via
            # Google Search, then writes using only verified facts, all in a
            # single call. The response carries a `sources` field we surface
            # to the manual-approval reviewer as factcheck.json.
            if format_name in GROUNDED_FORMATS:
                spec = script_lib.generate_grounded(full_prompt, format_name)
            else:
                spec = script_lib.generate(full_prompt)

        # If the grounded call returned a sources list, peel it off into
        # factcheck.json so reviewers can scan the citations without digging
        # through script.json. Pop it so it doesn't leak into the TTS script.
        sources = spec.pop("sources", None)
        if sources is not None:
            (out_dir / "factcheck.json").write_text(json.dumps({
                "format": format_name,
                "sources": sources,
            }, indent=2))

        script_path.write_text(json.dumps(spec, indent=2))

        if stage == "script":
            return out_dir
    else:
        # stage == "video": pick up where the script-only run left off.
        if not script_path.exists():
            raise FileNotFoundError(
                f"stage='video' but no script.json at {script_path}. "
                "Run stage='script' first (or download the script artifact)."
            )
        spec = json.loads(script_path.read_text())

    # 2. TTS (voiceover + SRT)
    audio_path = out_dir / "voice.mp3"
    srt_path = out_dir / "captions.srt"
    voice = voice_override or voice_for(format_name)
    tts.synthesize(spec["script"], voice, audio_path, srt_path, rate=rate_for(format_name))

    # 3. Visuals — one Pexels clip per beat-aligned query the model emitted.
    # We always append the format name as a final fallback query so even if
    # every model-emitted query misses Pexels, we still end up with at least
    # one usable clip.
    queries = spec.get("visual_queries") or []
    if not queries:
        # Back-compat: older scripts emit a single visual_query string
        legacy = spec.get("visual_query")
        if legacy:
            queries = [legacy]
    queries = [q for q in queries if isinstance(q, str) and q.strip()]
    queries.append(format_name.replace("_", " "))  # last-ditch fallback
    # De-dupe while preserving order
    queries = list(dict.fromkeys(queries))

    clips_dir = out_dir / "clips"
    clips = visuals.fetch_videos_multi(queries, clips_dir)
    if not clips:
        raise RuntimeError(f"No Pexels videos found for any of: {queries!r}")

    # 4. Assemble — transition style depends on format mood.
    video_path = out_dir / "video.mp4"
    assemble.assemble(
        clips=clips,
        audio=audio_path,
        srt=srt_path,
        output=video_path,
        music=assemble.find_music(format_name),
        transition=TRANSITION_BY_FORMAT.get(format_name, "crossfade"),
    )

    # 5. Metadata + suggested YouTube fields (so you can copy-paste at upload time)
    channel = load_channel()
    tags = list(dict.fromkeys(spec.get("hashtags", []) + channel.get("base_hashtags", [])))
    metadata = {
        "format": format_name,
        "title": spec["title"][:100],
        "description": _build_description(spec, channel),
        "tags": [t.lstrip("#") for t in tags],
        "video_path": str(video_path),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    # Record this title so future runs' "AVOID THESE" prompt block knows about it.
    # Done after a successful build (not at script stage) so rejected/never-built
    # scripts don't pollute the history.
    history.record(format_name, spec.get("title", ""), spec.get("premise", "") or spec.get("quote", ""))

    # 6. Drop intermediate files — captions are burned into the video and audio is
    # baked into the mp4. Keeping these in the artifact doubles its size for no benefit.
    import shutil
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
    for stale in (audio_path, srt_path):
        if stale.exists():
            stale.unlink()

    return out_dir


def _build_description(spec: dict, channel: dict) -> str:
    lines = [spec.get("script", "")]
    lines.append("")
    lines.append(channel.get("tagline", ""))
    lines.append("")
    lines.append(" ".join(spec.get("hashtags", []) + channel.get("base_hashtags", [])))
    return "\n".join(lines).strip()
