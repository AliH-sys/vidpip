from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import provider_config
from .logging_utils import get_logger
from .metadata import asset_metadata, claim, fail_story, find_asset, story_files
from .providers import transcribe_cloud

log = get_logger("subtitles")


def ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int(seconds % 3600 // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def write_ass(path: Path, segments: list[dict[str, Any]], style: str = "Default") -> None:
    header = """[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,3,1,5,60,60,180,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    lines = [header]
    for segment in segments:
        text = str(segment.get("text", "")).replace("{", "\\{").replace("}", "\\}").replace("\n", " ").strip()
        if text:
            lines.append(f"Dialogue: 0,{ass_time(float(segment['start']))},{ass_time(float(segment['end']))},{style},,0,0,0,,{text}\n")
    path.write_text("".join(lines), encoding="utf-8")


def transcribe_local(audio: Path, settings: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install faster-whisper for local subtitles") from exc
    device = settings.get("device", "auto")
    if device == "auto":
        device = "cuda" if __import__("importlib.util").util.find_spec("torch") and __import__("torch").cuda.is_available() else "cpu"
    model = WhisperModel(settings.get("model", "small"), device=device, compute_type=settings.get("compute_type", "int8"))
    segments, _ = model.transcribe(str(audio), language=settings.get("language"), word_timestamps=False)
    return [{"start": float(item.start), "end": float(item.end), "text": item.text} for item in segments]


def process_subtitles_once(config: dict[str, Any], dry_run: bool = False) -> int:
    root = Path(config["media_root"])
    settings = config["subtitles"]
    done = 0
    for folder in story_files(root, "notFinished"):
        audio = find_asset(folder, (".wav", ".mp3", ".flac"))
        if not audio or find_asset(folder, (".ass",)):
            continue
        with claim(folder, "subtitles") as acquired:
            if not acquired:
                continue
            try:
                output = folder / "subtitles.ass"
                if dry_run:
                    log.info("[dry-run] Would transcribe %s", audio)
                else:
                    if settings.get("mode") == "faster_whisper":
                        segments = transcribe_local(audio, settings)
                    elif settings.get("mode") == "cloud":
                        provider = provider_config(config, "subtitles", str(settings.get("model")))
                        segments = transcribe_cloud(provider, str(audio), settings.get("language"))
                    else:
                        raise RuntimeError(f"Unsupported subtitle mode: {settings.get('mode')}")
                    write_ass(output, segments, str(settings.get("style", "Default")))
                    asset_metadata(output, "subtitles", source=audio.name, provider=settings.get("mode"), format="ass", status="unused")
                done += 1
            except Exception as exc:
                fail_story(folder, "subtitles", str(exc), int(config.get("retry", {}).get("max_attempts", 3)))
                log.exception("Subtitle generation failed for %s: %s", folder.name, exc)
    return done
