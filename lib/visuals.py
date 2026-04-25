"""Pexels stock footage fetcher. Given a search query, downloads 1-2 vertical
videos to cover the Short's duration. Falls back to images if no video matches."""

import os
from pathlib import Path
import requests

_PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"
_PEXELS_PHOTO_SEARCH = "https://api.pexels.com/v1/search"


def _headers():
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY not set")
    return {"Authorization": key}


def fetch_videos(query: str, out_dir: Path, count: int = 2) -> list[Path]:
    """Download up to `count` vertical stock videos matching the query."""
    out_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(
        _PEXELS_VIDEO_SEARCH,
        headers=_headers(),
        params={"query": query, "orientation": "portrait", "per_page": max(count * 2, 5)},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    paths = []
    for i, video in enumerate(data.get("videos", [])):
        if len(paths) >= count:
            break
        # Pick the smallest HD-or-better vertical file
        files = sorted(
            [f for f in video["video_files"] if f.get("width", 0) <= f.get("height", 0)],
            key=lambda f: f.get("height", 0),
        )
        hd = next((f for f in files if f.get("height", 0) >= 1280), files[-1] if files else None)
        if not hd:
            continue
        path = out_dir / f"clip_{i}.mp4"
        with requests.get(hd["link"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(path, "wb") as fp:
                for chunk in r.iter_content(1 << 20):
                    fp.write(chunk)
        paths.append(path)
    return paths


def fetch_images(query: str, out_dir: Path, count: int = 3) -> list[Path]:
    """Fallback: fetch vertical photos (used when no stock video matches or as ken-burns source)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(
        _PEXELS_PHOTO_SEARCH,
        headers=_headers(),
        params={"query": query, "orientation": "portrait", "per_page": count},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    paths = []
    for i, photo in enumerate(data.get("photos", [])):
        path = out_dir / f"photo_{i}.jpg"
        with requests.get(photo["src"]["large2x"], stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(path, "wb") as fp:
                for chunk in r.iter_content(1 << 20):
                    fp.write(chunk)
        paths.append(path)
    return paths
