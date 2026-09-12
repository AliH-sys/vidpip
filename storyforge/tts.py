from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .config import provider_config
from .logging_utils import get_logger
from .media import ensure_media_tree
from .metadata import asset_metadata, claim, fail_story, find_asset, read_metadata
from .providers import synthesize_cloud

log = get_logger("tts")


def synthesize_local(mode: str, text: str, voice: str, output: Path, settings: dict[str, Any]) -> None:
    if mode == "kokoro":
        try:
            from kokoro import KPipeline
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("Install kokoro and soundfile for Kokoro TTS") from exc
        pipeline = KPipeline(lang_code=str(settings.get("language", "a")))
        chunks = [audio for _, _, audio in pipeline(text, voice=voice, speed=float(settings.get("speed", 1.0)))]
        if not chunks:
            raise RuntimeError("Kokoro produced no audio")
        import numpy as np
        sf.write(output, np.concatenate(chunks), 24000)
        return
    if mode == "chatterbox":
        try:
            from chatterbox.tts import ChatterboxTTS
            import torchaudio
        except ImportError as exc:
            raise RuntimeError("Install chatterbox-tts and torchaudio for Chatterbox TTS") from exc
        model = ChatterboxTTS.from_pretrained(device=str(settings.get("device", "cpu")))
        wav = model.generate(text)
        torchaudio.save(str(output), wav, model.sr)
        return
    raise RuntimeError(f"Unsupported local TTS mode: {mode}")


def process_tts_once(config: dict[str, Any], dry_run: bool = False) -> int:
    root = Path(config["media_root"])
    ensure_media_tree(root)
    settings = config["tts"]
    done = 0
    for folder in __import__("storyforge.metadata", fromlist=["story_files"]).story_files(root, "notFinished"):
        text = folder / "story.txt"
        if not text.exists() or find_asset(folder, (".wav", ".mp3", ".flac")):
            continue
        with claim(folder, "tts") as acquired:
            if not acquired:
                continue
            try:
                gender = read_metadata(text).get("gender", "female")
                voice = settings.get(f"{gender}_voice", "af_heart")
                output = folder / "voice.wav"
                if dry_run:
                    log.info("[dry-run] Would synthesize %s", text)
                elif settings.get("mode") in {"kokoro", "chatterbox"}:
                    synthesize_local(str(settings["mode"]), text.read_text(encoding="utf-8"), str(voice), output, settings)
                    asset_metadata(output, "voice", source=text.name, voice=voice, provider=settings["mode"], status="unused")
                elif settings.get("mode") == "cloud":
                    provider_name = str(settings.get("model"))
                    provider = provider_config(config, "tts", provider_name)
                    synthesize_cloud(provider, text.read_text(encoding="utf-8"), str(voice), str(output))
                    asset_metadata(output, "voice", source=text.name, voice=voice, provider=provider_name, status="unused")
                else:
                    raise RuntimeError(f"Unsupported TTS mode: {settings.get('mode')}")
                done += 1
            except Exception as exc:
                fail_story(folder, "tts", str(exc), int(config.get("retry", {}).get("max_attempts", 3)))
                log.exception("TTS failed for %s: %s", folder.name, exc)
    return done
