"""ffmpeg composition for a 9:16 Short.
Inputs: list of video clip paths + audio file + srt captions (+ optional bg music).
Output: one final .mp4 ready for upload."""

import subprocess
from pathlib import Path
from .config import video_dims, ASSETS_DIR


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
):
    """Concatenate clips, scale to 9:16, overlay audio, burn captions, mix bg music, output mp4."""
    W, H, FPS, MAX = video_dims()
    audio_dur = _probe_duration(audio)
    # Cap final duration at MAX seconds (Shorts limit safety)
    final_dur = min(audio_dur + 0.5, MAX)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Build filter graph: scale each clip to 9:16 with crop, concat them, loop if too short.
    clip_inputs = []
    for c in clips:
        clip_inputs.extend(["-stream_loop", "-1", "-i", str(c)])

    n = len(clips)
    scale_filters = []
    for i in range(n):
        scale_filters.append(
            f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},setsar=1,fps={FPS}[v{i}]"
        )
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    concat = f"{concat_inputs}concat=n={n}:v=1:a=0[vcat]"

    # Burn SRT captions (bottom-centered, large, white with black box for readability)
    srt_escaped = str(srt).replace(":", "\\:").replace("'", "\\'")
    caption = (
        f"[vcat]subtitles='{srt_escaped}'"
        f":force_style='FontName=Arial,FontSize=18,PrimaryColour=&HFFFFFF,"
        f"OutlineColour=&H000000,BorderStyle=1,Outline=3,Shadow=0,"
        f"Alignment=2,MarginV=180'[vcap]"
    )

    # Trim/pad to final_dur
    trim = f"[vcap]trim=0:{final_dur},setpts=PTS-STARTPTS[vout]"

    vf = ";".join(scale_filters + [concat, caption, trim])

    cmd = ["ffmpeg", "-y", *clip_inputs, "-i", str(audio)]
    audio_idx = n  # audio is after the n clip inputs
    music_idx = None
    if music and music.exists():
        cmd.extend(["-stream_loop", "-1", "-i", str(music)])
        music_idx = n + 1

    if music_idx is not None:
        # Duck bg music under voiceover
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


def find_music() -> Path | None:
    """Pick first music file in assets/music/ (user drops royalty-free tracks there)."""
    music_dir = ASSETS_DIR / "music"
    if not music_dir.exists():
        return None
    for ext in ("*.mp3", "*.m4a", "*.wav"):
        tracks = list(music_dir.glob(ext))
        if tracks:
            return tracks[0]
    return None
