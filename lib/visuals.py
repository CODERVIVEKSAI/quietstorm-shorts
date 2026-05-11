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


def _download_one(query: str, out_path: Path) -> bool:
    """Try to download a single vertical HD clip for `query`. Returns True
    on success, False if Pexels returned no usable result."""
    try:
        resp = requests.get(
            _PEXELS_VIDEO_SEARCH,
            headers=_headers(),
            params={"query": query, "orientation": "portrait", "per_page": 5},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[visuals] Pexels search failed for {query!r}: {e}")
        return False

    for video in resp.json().get("videos", []):
        files = sorted(
            [f for f in video.get("video_files", []) if f.get("width", 0) <= f.get("height", 0)],
            key=lambda f: f.get("height", 0),
        )
        hd = next((f for f in files if f.get("height", 0) >= 1280), files[-1] if files else None)
        if not hd:
            continue
        try:
            with requests.get(hd["link"], stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(out_path, "wb") as fp:
                    for chunk in r.iter_content(1 << 20):
                        fp.write(chunk)
            return True
        except Exception as e:
            print(f"[visuals] download failed for {query!r}: {e}")
            continue
    return False


def fetch_videos(query: str, out_dir: Path, count: int = 2) -> list[Path]:
    """Legacy single-query fetch — kept for back-compat. Prefer fetch_videos_multi."""
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


def fetch_videos_multi(queries: list[str], out_dir: Path) -> list[Path]:
    """Download one clip per query, in order. Each query that returns no
    Pexels results is silently skipped — the returned list may be shorter
    than `queries`. Use this with a per-format fallback query passed last
    so you always end up with at least one clip.

    File names are `clip_{i:02d}_{slugified_query}.mp4` so the order is
    preserved by alphabetical sort if anything downstream relies on that.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, query in enumerate(queries):
        if not query or not query.strip():
            continue
        slug = "".join(c if c.isalnum() else "_" for c in query.strip().lower())[:40]
        path = out_dir / f"clip_{i:02d}_{slug}.mp4"
        if _download_one(query, path):
            paths.append(path)
        else:
            print(f"[visuals] no Pexels match for query #{i} {query!r}; skipping slot")
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
