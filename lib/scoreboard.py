"""Render a 9:16 scoreboard graphic for sports recaps. Pure ffmpeg drawtext
— no Pillow dependency, no font shipped with the repo. Writes each text
segment to a temp file so we sidestep drawtext's escaping rules entirely.

Layout (top → bottom):
  - competition name (gray, small)
  - home team (white, large, uppercase)
  - SCORE — HOME  —  AWAY  (gold, huge)
  - away team (white, large, uppercase)
  - match date (gray, small)

If a required field (home/away team or score) is missing we raise; the
caller is expected to skip the scoreboard entirely in that case so the
rest of the video still builds.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

# Candidate bold fonts to use. First one found on disk wins. ffmpeg's drawtext
# filter needs an actual font file path — fontconfig lookup is unreliable on
# minimal runner images.
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _find_font() -> str:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise RuntimeError(
        "no bold font found on system — checked: " + ", ".join(_FONT_CANDIDATES)
    )


def render(
    match_info: dict,
    out_path: Path,
    *,
    duration: float = 2.8,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> Path:
    """Produce a static scoreboard MP4 at `out_path`. Returns the path."""
    home_team = (match_info.get("home_team") or "").strip()
    away_team = (match_info.get("away_team") or "").strip()
    home_score = str(match_info.get("home_score") or "").strip()
    away_score = str(match_info.get("away_score") or "").strip()
    if not (home_team and away_team and home_score and away_score):
        raise ValueError(
            "match_info needs home_team, away_team, home_score, away_score"
        )

    competition = (match_info.get("competition") or "").strip()
    match_date = (match_info.get("match_date") or "").strip()

    font_path = _find_font()
    tmp_dir = Path(tempfile.mkdtemp(prefix="scoreboard_"))

    def write_segment(name: str, content: str) -> Path:
        p = tmp_dir / f"{name}.txt"
        p.write_text(content, encoding="utf-8")
        return p

    score_line = f"{home_score}   —   {away_score}"

    y_center = height // 2

    drawtexts: list[str] = []

    def add(name: str, content: str, color: str, size: int, y_offset: int):
        path = write_segment(name, content)
        drawtexts.append(
            f"drawtext=fontfile='{font_path}':textfile='{path}':"
            f"fontcolor={color}:fontsize={size}:"
            f"x=(w-text_w)/2:y={y_center + y_offset}"
        )

    if competition:
        add("comp", competition.upper(), "0xCCCCCC", 44, -460)
    add("home", home_team.upper(), "white", 92, -260)
    add("score", score_line, "0xFFD24A", 200, -60)
    add("away", away_team.upper(), "white", 92, 240)
    if match_date:
        add("date", match_date, "0x999999", 44, 460)

    vf = ",".join(drawtexts)
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x0A1628:s={width}x{height}:d={duration:.3f}:r={fps}",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"scoreboard ffmpeg failed:\nCMD: {' '.join(cmd)}\n"
                f"STDERR: {result.stderr[-1500:]}"
            )
        return out_path
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
