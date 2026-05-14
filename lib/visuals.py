"""Pexels stock footage fetcher. Given a search query, downloads vertical
videos to cover the Short's duration.

Variety strategy: every Pexels search is randomized across page 1-3 with
per_page=15, then we shuffle the results before picking a clip. That gives
~60 candidates per query instead of always grabbing the top-ranked video,
so two shorts sharing a query (or the per-format fallback like "football")
don't collide on the same clip. Within a single run we also dedupe by
Pexels video ID so different beats in one video don't reuse the same clip.
"""

import os
import random
from pathlib import Path
import requests

_PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"
_PEXELS_PHOTO_SEARCH = "https://api.pexels.com/v1/search"


def _headers():
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        raise RuntimeError("PEXELS_API_KEY not set")
    return {"Authorization": key}


def _search(query: str, page: int, per_page: int = 15) -> list[dict]:
    try:
        resp = requests.get(
            _PEXELS_VIDEO_SEARCH,
            headers=_headers(),
            params={
                "query": query,
                "orientation": "portrait",
                "per_page": per_page,
                "page": page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("videos", []) or []
    except Exception as e:
        print(f"[visuals] Pexels search failed for {query!r} (page {page}): {e}")
        return []


def _best_hd_file(video: dict) -> dict | None:
    files = sorted(
        [f for f in video.get("video_files", []) if f.get("width", 0) <= f.get("height", 0)],
        key=lambda f: f.get("height", 0),
    )
    return next((f for f in files if f.get("height", 0) >= 1280), files[-1] if files else None)


def _download_to(hd: dict, out_path: Path) -> bool:
    try:
        with requests.get(hd["link"], stream=True, timeout=120) as r:
            r.raise_for_status()
            with open(out_path, "wb") as fp:
                for chunk in r.iter_content(1 << 20):
                    fp.write(chunk)
        return True
    except Exception as e:
        print(f"[visuals] download failed: {e}")
        return False


def _download_one(query: str, out_path: Path, used_ids: set[int] | None = None) -> int | None:
    """Try a few random pages, pick an HD vertical clip that's not in
    `used_ids`. Returns the Pexels video id on success (so the caller can
    track it), or None if no usable clip was found."""
    used_ids = used_ids or set()
    pages = [1, 2, 3]
    random.shuffle(pages)
    for page in pages:
        videos = _search(query, page=page)
        if not videos:
            continue
        # Filter out clips already used in this run, then shuffle so two
        # consecutive runs with the same query don't repeatedly land on the
        # same top result.
        fresh = [v for v in videos if v.get("id") not in used_ids]
        pool = fresh if fresh else videos
        random.shuffle(pool)
        for video in pool:
            hd = _best_hd_file(video)
            if not hd:
                continue
            if _download_to(hd, out_path):
                return video.get("id")
    return None


def fetch_videos(query: str, out_dir: Path, count: int = 2) -> list[Path]:
    """Legacy single-query fetch — kept for back-compat. Prefer
    fetch_videos_multi. Now routes through _download_one so it gets the same
    randomized-page + within-run dedupe behavior."""
    out_dir.mkdir(parents=True, exist_ok=True)
    used_ids: set[int] = set()
    paths: list[Path] = []
    for i in range(count):
        path = out_dir / f"clip_{i}.mp4"
        vid_id = _download_one(query, path, used_ids=used_ids)
        if not vid_id:
            break
        used_ids.add(vid_id)
        paths.append(path)
    return paths


def fetch_videos_multi(queries: list[str], out_dir: Path) -> list[Path]:
    """Download one clip per query, in order. Each query that returns no
    Pexels results is silently skipped — the returned list may be shorter
    than `queries`. Use this with a per-format fallback query passed last
    so you always end up with at least one clip.

    Tracks Pexels video IDs already pulled in this run so different beats
    in the same video don't share a clip (e.g. two queries that both lean
    toward stadium night don't both grab the same #1 stadium-night video).

    File names are `clip_{i:02d}_{slugified_query}.mp4` so the order is
    preserved by alphabetical sort if anything downstream relies on that.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    used_ids: set[int] = set()
    for i, query in enumerate(queries):
        if not query or not query.strip():
            continue
        slug = "".join(c if c.isalnum() else "_" for c in query.strip().lower())[:40]
        path = out_dir / f"clip_{i:02d}_{slug}.mp4"
        vid_id = _download_one(query, path, used_ids=used_ids)
        if vid_id:
            used_ids.add(vid_id)
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
