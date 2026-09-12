from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any


def checks(config: dict[str, Any]) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    root = Path(config["media_root"])
    results.append(("media root writable", root.exists() or root.parent.exists(), str(root)))
    results.append(("ffmpeg available", shutil.which(str(config["composer"].get("ffmpeg", "ffmpeg"))) is not None, "required for final videos"))
    for module in ("yaml", "dotenv", "urwid", "yt_dlp", "openai", "psutil"):
        results.append((f"python package: {module}", importlib.util.find_spec(module) is not None, ""))
    if config["tts"].get("mode") == "kokoro":
        results.append(("Kokoro package", importlib.util.find_spec("kokoro") is not None, "selected TTS backend"))
    if config["subtitles"].get("mode") == "faster_whisper":
        results.append(("faster-whisper package", importlib.util.find_spec("faster_whisper") is not None, "selected subtitle backend"))
    return results


def run_doctor(config: dict[str, Any]) -> int:
    failed = 0
    for name, okay, detail in checks(config):
        print(f"[{'OK' if okay else 'FAIL'}] {name} {detail}")
        failed += not okay
    return int(failed)
