"""edge-tts voiceover. Produces an MP3 plus an SRT caption file.

Captions are built deterministically from the script text + audio duration
(rather than relying on edge-tts's SubMaker word-boundary events, whose API
changes between minor versions). Splits the script into ~4-word cues and
distributes timing proportional to character count.

Also sanitizes scripts before synthesis: TTS engines spell out non-word
interjections (ARRRGGHHH, OOOMG, AAAAH) letter-by-letter, so we substitute
them with proper words the engine actually voices.

Note on inline SSML: edge-tts 7.x XML-escapes the input before wrapping it
in <speak>/<voice>/<prosody>, so any <prosody>/<break> tags we tried to
inject got escaped and spoken literally (the user heard "minus seven percent
pitch plus eight percent"). We pass plain text and let edge-tts handle
top-level prosody via rate/pitch/volume args. Per-phrase emphasis isn't
achievable through this library; the `emphasis_phrases` arg is accepted but
ignored, kept so callers don't break.
"""

import asyncio
import re
import subprocess
from pathlib import Path
import edge_tts


# Stylized interjections → real words the TTS engine pronounces correctly.
# Patterns are case-insensitive; replacement preserves first-letter capitalization.
_INTERJECTION_PATTERNS = [
    (re.compile(r"\bA+R+G+H+\b", re.IGNORECASE), "Argh"),
    (re.compile(r"\bA+[Hh]+\b", re.IGNORECASE), "Ahh"),
    (re.compile(r"\bA+W+\b", re.IGNORECASE), "Aww"),
    (re.compile(r"\bO+M+G+\b", re.IGNORECASE), "OMG"),
    (re.compile(r"\bU+G+H+\b", re.IGNORECASE), "Ugh"),
    (re.compile(r"\bY+A+Y+\b", re.IGNORECASE), "Yay"),
    (re.compile(r"\b[Hh][Aa]{2,}\b"), "Haha"),
    (re.compile(r"\bW+O+W+\b", re.IGNORECASE), "Wow"),
    (re.compile(r"\bE+K+\b", re.IGNORECASE), "Eek"),
    (re.compile(r"\bO+O+P+S+\b", re.IGNORECASE), "Oops"),
    (re.compile(r"\bH+M+\b", re.IGNORECASE), "Hmm"),
    (re.compile(r"\bP+F+T+\b", re.IGNORECASE), "Pfft"),
    (re.compile(r"\bN+O+P+E+\b", re.IGNORECASE), "Nope"),
]

# Generic safety net: collapse 3+ identical letters in any word down to 2.
# "loooong" → "loong", "soooo" → "soo". Most English words don't have triples.
_TRIPLE_LETTERS = re.compile(r"([a-zA-Z])\1{2,}")


def sanitize_for_tts(text: str) -> str:
    """Make scripts safe for TTS by replacing stylized exclamations and collapsing
    runs of repeated letters."""
    for pattern, repl in _INTERJECTION_PATTERNS:
        text = pattern.sub(repl, text)
    text = _TRIPLE_LETTERS.sub(r"\1\1", text)
    return text


async def _synthesize_audio(
    text: str,
    voice: str,
    audio_path: Path,
    *,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%",
):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
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


def synthesize(
    text: str,
    voice: str,
    audio_path: Path,
    srt_path: Path,
    *,
    rate: str = "+0%",
    pitch: str = "+0Hz",
    volume: str = "+0%",
    emphasis_phrases: list[str] | None = None,   # accepted, ignored — see module docstring
):
    """Synthesize voiceover MP3 + write a time-proportional SRT caption file.

    Args other than the obvious ones:
      rate    — edge-tts speech rate, e.g. "+0%", "-7%", "+12%"
      pitch   — edge-tts pitch offset in Hz, e.g. "+5Hz", "-3Hz"
      volume  — edge-tts volume offset, e.g. "+10%"

    Captions are built from the sanitized text so what's burned into the
    video matches what the viewer hears, character-for-character.
    """
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    plain = sanitize_for_tts(text)
    asyncio.run(_synthesize_audio(
        plain, voice, audio_path,
        rate=rate, pitch=pitch, volume=volume,
    ))
    duration = _audio_duration(audio_path)
    srt_path.write_text(_build_srt(plain, duration))
