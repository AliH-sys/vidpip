from __future__ import annotations

import random
import shutil
from pathlib import Path

from .metadata import read_metadata, update_metadata

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov"}


def ensure_media_tree(root: Path) -> None:
    for path in (root / "background_videos", root / "stories" / "notFinished", root / "stories" / "finished", root / "stories" / "failed"):
        path.mkdir(parents=True, exist_ok=True)


def media_files(folder: Path) -> list[Path]:
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS), key=lambda p: p.stat().st_mtime) if folder.exists() else []


def choose_background(root: Path, max_uses: int) -> Path | None:
    candidates = media_files(root / "background_videos")
    eligible = [p for p in candidates if int(read_metadata(p).get("use_count", 0)) < max_uses]
    return random.choice(eligible) if eligible else None


def record_background_use(path: Path, max_uses: int) -> None:
    data = read_metadata(path)
    uses = int(data.get("use_count", 0)) + 1
    update_metadata(path, status="used", use_count=uses, last_used_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat())
    if uses >= max_uses:
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".json").unlink(missing_ok=True)


def prune_background(root: Path, target: int, max_uses: int) -> int:
    files = media_files(root / "background_videos")
    removed = 0
    # Used-at-limit files are removed first; then oldest files if an exact target is required.
    ordered = sorted(files, key=lambda p: (int(read_metadata(p).get("use_count", 0)) < max_uses, p.stat().st_mtime))
    for path in ordered:
        remaining = len(media_files(root / "background_videos"))
        if remaining <= target:
            break
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".json").unlink(missing_ok=True)
        removed += 1
    return removed
