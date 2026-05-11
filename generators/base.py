"""Shared build pipeline for every format: script -> tts -> visuals -> assemble."""

import json
from pathlib import Path
from lib import script as script_lib
from lib import tts, visuals, assemble
from lib.config import load_channel, voice_for, rate_for, OUTPUT_DIR
from lib.preferences import preferences_block
from lib.style import WRITING_RULES
from lib import history
from lib import factcheck

# Formats whose scripts go through the fact-check loop before audio/video
# is built. Jokes are deliberately absurd so they're skipped — verifying
# "what if everyone in the group chat went silent" is a category error.
FACT_CHECK_FORMATS = {"what_if", "quote", "cricket", "football", "golden_lady", "custom"}

# Cap on how many revise→re-verify rounds we'll do. Without a cap, a script
# that makes one un-Google-able claim could loop forever.
MAX_FACT_CHECK_ITERATIONS = 5


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
            spec = script_lib.generate(full_prompt)

        # Fact-check loop. Only fact-heavy formats go through it, and only when
        # a NEW script was generated (edit instructions get re-verified too —
        # the edit could have introduced new false claims). Two independent
        # passes per round; we revise until both say clean, or until we hit
        # MAX_FACT_CHECK_ITERATIONS and fail loudly so the bad script doesn't
        # silently make it through to the approval gate.
        fc_report = None
        if format_name in FACT_CHECK_FORMATS:
            for iteration in range(1, MAX_FACT_CHECK_ITERATIONS + 1):
                print(f"[factcheck] {format_name} iteration {iteration}/{MAX_FACT_CHECK_ITERATIONS}")
                report = factcheck.verify_twice(spec.get("script", ""), format_name)
                report["_iteration"] = iteration
                fc_report = report
                if report["ok"]:
                    print(f"[factcheck] {format_name} verified clean on iteration {iteration}")
                    break
                if iteration == MAX_FACT_CHECK_ITERATIONS:
                    # Save the report so the user can see what kept failing,
                    # then raise so the workflow fails the script job.
                    (out_dir / "factcheck.json").write_text(json.dumps(report, indent=2))
                    (out_dir / "script.json").write_text(json.dumps(spec, indent=2))
                    raise RuntimeError(
                        f"fact-check did not converge for {format_name} after "
                        f"{MAX_FACT_CHECK_ITERATIONS} iterations. "
                        f"Remaining issues: {report.get('issues')}"
                    )
                print(f"[factcheck] {format_name} found {len(report.get('issues', []))} "
                      f"issue(s); revising and re-checking…")
                spec = script_lib.revise_for_facts(spec, report.get("issues", []), format_name)

            (out_dir / "factcheck.json").write_text(json.dumps(fc_report, indent=2))

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
