"""edge-tts voiceover. Produces an MP3 + an SRT caption file with per-word timing
(used by ffmpeg to burn captions into the video)."""

import asyncio
from pathlib import Path
import edge_tts


async def _synthesize(text: str, voice: str, audio_path: Path, srt_path: Path):
    communicate = edge_tts.Communicate(text, voice)
    submaker = edge_tts.SubMaker()
    with open(audio_path, "wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                submaker.feed(chunk)
    srt_path.write_text(submaker.get_srt())


def synthesize(text: str, voice: str, audio_path: Path, srt_path: Path):
    """Synchronous wrapper. Writes audio (mp3) and srt captions."""
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_synthesize(text, voice, audio_path, srt_path))
