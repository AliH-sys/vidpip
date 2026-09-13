from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".json")


def write_metadata(path: Path, data: dict[str, Any]) -> None:
    target = sidecar(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(data)
    payload.setdefault("updated_at", now())
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, target)


def read_metadata(path: Path) -> dict[str, Any]:
    target = sidecar(path) if path.suffix != ".json" else path
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def update_metadata(path: Path, **changes: Any) -> dict[str, Any]:
    data = read_metadata(path)
    data.update(changes)
    data["updated_at"] = now()
    write_metadata(path, data)
    return data


def asset_metadata(path: Path, kind: str, **extra: Any) -> dict[str, Any]:
    data = {"asset": path.name, "kind": kind, "status": "unused", "created_at": now(), **extra}
    write_metadata(path, data)
    return data


def story_id() -> str:
    return f"story-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def story_files(root: Path, stage: str = "notFinished") -> list[Path]:
    folder = root / "stories" / stage
    return sorted((p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")), key=lambda p: p.stat().st_mtime) if folder.exists() else []


def find_asset(folder: Path, suffixes: tuple[str, ...]) -> Path | None:
    for path in sorted(folder.iterdir()) if folder.exists() else []:
        if path.is_file() and path.suffix.lower() in suffixes and not path.name.endswith(".json"):
            return path
    return None


@contextmanager
def claim(folder: Path, stage: str) -> Iterator[bool]:
    """Claim a story using an atomic lock directory; safe across independent processes."""
    lock = folder / f".{stage}.lock"
    acquired = False
    try:
        lock.mkdir()
        acquired = True
        yield True
    except FileExistsError:
        yield False
    finally:
        if acquired:
            shutil.rmtree(lock, ignore_errors=True)


def create_story(root: Path, payload: dict[str, Any], prompt: str, provider: str) -> Path:
    folder = root / "stories" / "notFinished" / story_id()
    folder.mkdir(parents=True, exist_ok=False)
    text = folder / "story.txt"
    text.write_text(payload["story"].strip() + "\n", encoding="utf-8")
    data = {"kind": "story", "status": "unused", "title": payload["title"], "description": payload["description"], "tags": payload["tags"], "gender": payload["gender"], "prompt": prompt, "provider": provider, "retry_count": 0, "created_at": now()}
    write_metadata(text, data)
    return folder


def fail_story(folder: Path, stage: str, error: str, max_attempts: int) -> Path:
    meta_path = folder / "story.txt"
    data = read_metadata(meta_path)
    attempts = int(data.get("retry_count", 0)) + 1
    data.update({"status": "failed", "failed_stage": stage, "last_error": error[-2000:], "retry_count": attempts, "failed_at": now()})
    write_metadata(meta_path, data)
    target = folder
    if folder.parent.name != "failed":
        target = folder.parents[1] / "failed" / folder.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(folder), str(target))
    return target


def retry_failed(root: Path, max_attempts: int) -> tuple[int, int]:
    retried = deleted = 0
    for folder in story_files(root, "failed"):
        data = read_metadata(folder / "story.txt")
        attempts = int(data.get("retry_count", 0))
        # retry_count records failures; max_attempts includes the current attempt.
        if attempts >= max_attempts - 1:
            shutil.rmtree(folder, ignore_errors=True)
            deleted += 1
            continue
        data.update({"status": "unused", "retry_ready_at": now()})
        write_metadata(folder / "story.txt", data)
        target = root / "stories" / "notFinished" / folder.name
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(folder), str(target))
        retried += 1
    return retried, deleted


def stats(root: Path) -> dict[str, int]:
    counts = {"stories": 0, "finished": 0, "failed": 0, "audio": 0, "subtitles": 0, "videos": 0, "background": 0}
    for stage, key in (("notFinished", "stories"), ("finished", "finished"), ("failed", "failed")):
        for folder in story_files(root, stage):
            counts[key] += 1
            counts["audio"] += len(list(folder.glob("*.wav")))
            counts["subtitles"] += len(list(folder.glob("*.ass")))
    bg = root / "background_videos"
    counts["background"] = len([p for p in bg.iterdir() if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]) if bg.exists() else 0
    counts["videos"] = len([p for p in root.iterdir() if p.is_file() and p.suffix.lower() in {".mp4", ".mkv", ".webm"}]) if root.exists() else 0
    return counts
