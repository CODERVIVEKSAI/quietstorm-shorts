"""edge-tts voiceover. Produces an MP3 plus an SRT caption file.

Captions are built deterministically from the script text + audio duration
(rather than relying on edge-tts's SubMaker word-boundary events, whose API
changes between minor versions). Splits the script into ~4-word cues and
distributes timing proportional to character count.
"""

import asyncio
import subprocess
from pathlib import Path
import edge_tts


async def _synthesize_audio(text: str, voice: str, audio_path: Path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(audio_path))


def _audio_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    )
    return float(out.strip())


def _format_ts(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def _build_srt(text: str, duration: float, words_per_cue: int = 4) -> str:
    words = text.split()
    if not words:
        return ""
    chunks = [" ".join(words[i:i + words_per_cue]) for i in range(0, len(words), words_per_cue)]
    total_chars = sum(len(c) for c in chunks) or 1
    cues = []
    t = 0.0
    for i, chunk in enumerate(chunks):
        dt = duration * (len(chunk) / total_chars)
        start, end = t, t + dt
        t = end
        cues.append(f"{i + 1}\n{_format_ts(start)} --> {_format_ts(end)}\n{chunk}\n")
    return "\n".join(cues)


def synthesize(text: str, voice: str, audio_path: Path, srt_path: Path):
    """Synthesize voiceover MP3 + write a time-proportional SRT caption file."""
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_synthesize_audio(text, voice, audio_path))
    duration = _audio_duration(audio_path)
    srt_path.write_text(_build_srt(text, duration))
