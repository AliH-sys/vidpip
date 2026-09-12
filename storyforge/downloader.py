from __future__ import annotations

from pathlib import Path
from typing import Any

from .logging_utils import get_logger
from .media import ensure_media_tree, media_files, prune_background
from .metadata import asset_metadata

log = get_logger("downloader")


def download_once(config: dict[str, Any], dry_run: bool = False) -> int:
    root = Path(config["media_root"])
    settings = config["downloader"]
    ensure_media_tree(root)
    urls = [str(url).strip() for url in settings.get("urls", []) if str(url).strip()]
    current = len(media_files(root / "background_videos"))
    target = int(settings.get("target_count", 0))
    needed = max(0, target - current)
    if needed == 0:
        if settings.get("prune_over_target", True):
            removed = prune_background(root, target, int(settings.get("max_video_uses", 3))) if not dry_run else 0
            log.info("Background pool at target (%s); pruned %s", target, removed)
        return 0
    if not urls:
        log.warning("Background target is %s but downloader.urls is empty", target)
        return 0
    if dry_run:
        log.info("[dry-run] Would download up to %s background videos", min(needed, len(urls)))
        return min(needed, len(urls))
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("Install yt-dlp to use the downloader") from exc
    downloaded = 0
    options = {"format": settings.get("format"), "outtmpl": str(root / "background_videos" / "%(id)s.%(ext)s"), "noplaylist": True, "quiet": True, "no_warnings": True, "restrictfilenames": True, "merge_output_format": "mp4"}
    for url in urls:
        if downloaded >= needed:
            break
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
                if not path.exists():
                    path = Path(ydl.prepare_filename(info))
                if path.exists() and not path.with_name(path.name + ".json").exists():
                    asset_metadata(path, "background_video", source_url=url, title=info.get("title"), duration=info.get("duration"), use_count=0, status="unused")
                    downloaded += 1
                    log.info("Downloaded background %s", path.name)
        except Exception as exc:
            log.exception("Failed downloading %s: %s", url, exc)
    if settings.get("prune_over_target", True):
        prune_background(root, target, int(settings.get("max_video_uses", 3)))
    return downloaded
