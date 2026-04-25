"""Shared build pipeline for every format: script -> tts -> visuals -> assemble."""

import json
from pathlib import Path
from lib import script as script_lib
from lib import tts, visuals, assemble
from lib.config import load_channel, voice_for, rate_for, OUTPUT_DIR
from lib.preferences import preferences_block
from lib.style import WRITING_RULES


def build(format_name: str, prompt: str, run_id: str, edit_instruction: str | None = None,
          previous_script: dict | None = None, voice_override: str | None = None) -> Path:
    """Run the full pipeline for one video. Returns the path to the output directory
    (containing video.mp4 and metadata.json)."""

    out_dir = OUTPUT_DIR / run_id / format_name
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Script — every prompt gets the channel-wide writing rules + any
    # learned user preferences for this format prepended.
    if edit_instruction and previous_script:
        spec = script_lib.edit(previous_script, edit_instruction, format_name)
    else:
        prefs = preferences_block(format_name)
        full_prompt = WRITING_RULES + "\n" + prompt.rstrip()
        if prefs:
            full_prompt += "\n" + prefs
        spec = script_lib.generate(full_prompt)

    (out_dir / "script.json").write_text(json.dumps(spec, indent=2))

    # 2. TTS (voiceover + SRT)
    audio_path = out_dir / "voice.mp3"
    srt_path = out_dir / "captions.srt"
    voice = voice_override or voice_for(format_name)
    tts.synthesize(spec["script"], voice, audio_path, srt_path, rate=rate_for(format_name))

    # 3. Visuals
    query = spec.get("visual_query", format_name)
    clips_dir = out_dir / "clips"
    clips = visuals.fetch_videos(query, clips_dir, count=2)
    if not clips:
        # Fallback: photos (assemble.py treats them same way via ffmpeg input; keep minimal MVP:
        # if zero clips, raise so the workflow fails loudly rather than ship a broken video.)
        raise RuntimeError(f"No Pexels videos found for query: {query!r}")

    # 4. Assemble
    video_path = out_dir / "video.mp4"
    assemble.assemble(
        clips=clips,
        audio=audio_path,
        srt=srt_path,
        output=video_path,
        music=assemble.find_music(format_name),
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

    # 6. Drop intermediate clips to keep artifact size small (final mp4 already has them baked in)
    import shutil
    if clips_dir.exists():
        shutil.rmtree(clips_dir)

    return out_dir


def _build_description(spec: dict, channel: dict) -> str:
    lines = [spec.get("script", "")]
    lines.append("")
    lines.append(channel.get("tagline", ""))
    lines.append("")
    lines.append(" ".join(spec.get("hashtags", []) + channel.get("base_hashtags", [])))
    return "\n".join(lines).strip()
