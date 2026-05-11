"""ffmpeg composition for a 9:16 Short.

Inputs: list of video clip paths + audio file + srt captions (+ optional bg music).
Output: one final .mp4 ready for upload.

The clip-handling rules:
  - Each clip gets its own equal-sized slot of the final timeline.
  - Clips that are shorter than their slot are looped FRAME-WISE *only within
    that slot* (using the `loop` video filter), never globally — so you don't
    see the same clip play for the whole video.
  - Transitions between clips are either crossfade (xfade) or a hard cut, set
    per-format by the caller. Sports/jokes get hard cuts (punchier), chill
    formats get crossfade (softer).
"""

import subprocess
from pathlib import Path
from .config import video_dims, ASSETS_DIR

# Crossfade length in seconds. Half a second feels classy without dragging.
XFADE_DUR = 0.5


def _run(cmd: list[str]):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\nCMD: {' '.join(cmd)}\nSTDERR: {result.stderr[-2000:]}")


def _probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    )
    return float(out.strip())


def assemble(
    clips: list[Path],
    audio: Path,
    srt: Path,
    output: Path,
    music: Path | None = None,
    title_text: str | None = None,
    transition: str = "crossfade",
):
    """Compose the final 9:16 mp4.

    `transition`:
      - "crossfade" — xfade dissolve between adjacent clips (XFADE_DUR each)
      - "cut"       — hard cuts (concat). Punchier; best for jokes/sports.

    If only one clip is provided, transitions are a no-op.
    """
    if not clips:
        raise ValueError("assemble() needs at least one clip")
    if transition not in ("crossfade", "cut"):
        raise ValueError(f"unknown transition: {transition!r}")

    W, H, FPS, MAX = video_dims()
    audio_dur = _probe_duration(audio)
    final_dur = min(audio_dur + 0.5, MAX)
    output.parent.mkdir(parents=True, exist_ok=True)

    n = len(clips)

    # Per-clip slot length. With crossfade chaining, each adjacent transition
    # eats `XFADE_DUR` from the running output, so each clip needs to be a
    # touch longer to compensate. With hard cuts it's a clean divide.
    if transition == "crossfade" and n > 1:
        clip_len = (final_dur + (n - 1) * XFADE_DUR) / n
    else:
        clip_len = final_dur / n

    # Build the per-clip prep filters. `loop=-1:size=99999:start=0` makes the
    # filter loop frames inside this clip's slot if the source is shorter than
    # `clip_len` — frame-level looping is invisible to the viewer, unlike
    # restarting the whole clip from t=0 which is the old behavior we're
    # killing here.
    prep = []
    for i in range(n):
        prep.append(
            f"[{i}:v]"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},"
            f"setsar=1,"
            f"fps={FPS},"
            f"loop=loop=-1:size=99999:start=0,"
            f"trim=0:{clip_len:.3f},"
            f"setpts=PTS-STARTPTS"
            f"[v{i}]"
        )

    # Combine clips into one stream [vchain].
    if n == 1:
        combine = ["[v0]null[vchain]"]
    elif transition == "cut":
        concat_inputs = "".join(f"[v{i}]" for i in range(n))
        combine = [f"{concat_inputs}concat=n={n}:v=1:a=0[vchain]"]
    else:  # crossfade
        # xfade `offset` is the time *in the running chain* where the
        # transition begins. After each xfade, the chain's duration grows by
        # (clip_len - XFADE_DUR) — i.e. one new clip minus the overlap eaten
        # by the fade.
        combine = []
        prev_label = "v0"
        running = clip_len
        for i in range(1, n):
            out_label = f"x{i}" if i < n - 1 else "vchain"
            offset = running - XFADE_DUR
            combine.append(
                f"[{prev_label}][v{i}]xfade=transition=fade:"
                f"duration={XFADE_DUR}:offset={offset:.3f}[{out_label}]"
            )
            running += clip_len - XFADE_DUR
            prev_label = out_label

    # Burn SRT captions (bottom-centered, large, white with black outline)
    srt_escaped = str(srt).replace(":", "\\:").replace("'", "\\'")
    caption = (
        f"[vchain]subtitles='{srt_escaped}'"
        f":force_style='FontName=Arial,FontSize=18,PrimaryColour=&HFFFFFF,"
        f"OutlineColour=&H000000,BorderStyle=1,Outline=3,Shadow=0,"
        f"Alignment=2,MarginV=180'[vcap]"
    )

    # Trim/pad to final_dur
    trim = f"[vcap]trim=0:{final_dur:.3f},setpts=PTS-STARTPTS[vout]"

    vf = ";".join(prep + combine + [caption, trim])

    # ffmpeg input args: each clip as a regular input (NO -stream_loop — the
    # loop filter inside the graph handles slot-internal looping).
    clip_inputs: list[str] = []
    for c in clips:
        clip_inputs.extend(["-i", str(c)])

    cmd: list[str] = ["ffmpeg", "-y", *clip_inputs, "-i", str(audio)]
    audio_idx = n
    music_idx: int | None = None
    if music and music.exists():
        cmd.extend(["-stream_loop", "-1", "-i", str(music)])
        music_idx = n + 1

    if music_idx is not None:
        af = (
            f"[{audio_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[voice];"
            f"[{music_idx}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"volume=0.12[bg];"
            f"[voice][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        vf_full = vf + ";" + af
        cmd.extend([
            "-filter_complex", vf_full,
            "-map", "[vout]", "-map", "[aout]",
        ])
    else:
        cmd.extend([
            "-filter_complex", vf,
            "-map", "[vout]", "-map", f"{audio_idx}:a",
        ])

    cmd.extend([
        "-t", f"{final_dur}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(output),
    ])

    _run(cmd)
    return output


def find_music(format_name: str | None = None) -> Path | None:
    """Pick a music file. Prefers a format-specific track at assets/music/<format>/,
    then falls back to anything in assets/music/."""
    music_dir = ASSETS_DIR / "music"
    if not music_dir.exists():
        return None
    candidates: list[Path] = []
    if format_name:
        per_format = music_dir / format_name
        if per_format.exists():
            candidates.append(per_format)
    candidates.append(music_dir)
    for d in candidates:
        for ext in ("*.mp3", "*.m4a", "*.wav"):
            tracks = sorted(d.glob(ext))
            if tracks:
                return tracks[0]
    return None
