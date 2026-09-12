from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .logging_utils import get_logger
from .media import choose_background, record_background_use
from .metadata import asset_metadata, claim, fail_story, find_asset, read_metadata, story_files

log = get_logger("composer")


def compose_once(config: dict[str, Any], dry_run: bool = False) -> int:
    root = Path(config["media_root"])
    settings = config["composer"]
    max_uses = int(config["downloader"].get("max_video_uses", 3))
    done = 0
    for folder in story_files(root, "notFinished"):
        audio = find_asset(folder, (".wav", ".mp3", ".flac"))
        subtitles = find_asset(folder, (".ass",))
        if not audio or not subtitles or (root / f"{folder.name}.mp4").exists():
            continue
        with claim(folder, "composer") as acquired:
            if not acquired:
                continue
            background = choose_background(root, max_uses)
            if not background:
                log.warning("No eligible background video for %s", folder.name)
                continue
            try:
                output = root / f"{folder.name}.mp4"
                escaped_ass = str(subtitles).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
                command = [str(settings.get("ffmpeg", "ffmpeg")), "-y", "-stream_loop", "-1", "-i", str(background), "-i", str(audio), "-vf", f"scale={settings.get('output_width', 1080)}:{settings.get('output_height', 1920)}:force_original_aspect_ratio=increase,crop={settings.get('output_width', 1080)}:{settings.get('output_height', 1920)},ass='{escaped_ass}'", "-map", "0:v:0", "-map", "1:a:0", "-r", str(settings.get("fps", 30)), "-c:v", "libx264", "-preset", str(settings.get("preset", "medium")), "-crf", str(settings.get("crf", 20)), "-c:a", "aac", "-shortest", str(output)]
                if dry_run:
                    log.info("[dry-run] Would compose %s with %s", folder.name, background.name)
                else:
                    subprocess.run(command, check=True, capture_output=True, text=True)
                    asset_metadata(output, "final_video", story=folder.name, background=background.name, audio=audio.name, subtitles=subtitles.name, status="used")
                    record_background_use(background, max_uses)
                    target = root / "stories" / "finished" / folder.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    folder.rename(target)
                    log.info("Finished video %s", target / output.name)
                done += 1
            except Exception as exc:
                fail_story(folder, "composer", str(exc), int(config.get("retry", {}).get("max_attempts", 3)))
                log.exception("Composition failed for %s: %s", folder.name, exc)
    return done
