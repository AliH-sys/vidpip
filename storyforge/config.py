from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml
try:
    from dotenv import dotenv_values, load_dotenv
except ImportError:  # Keep init/doctor usable before optional dependencies are installed.
    def load_dotenv(path: str | Path, override: bool = False) -> None:
        path = Path(path)
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if override or key.strip() not in os.environ:
                os.environ[key.strip()] = value.strip().strip('\\"\\\'')

    def dotenv_values(path: str | Path) -> dict[str, str]:
        path = Path(path)
        if not path.exists():
            return {}
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('\\"\\\'')
        return values

"""Configuration loading helpers."""


DEFAULTS: dict[str, Any] = {
    "media_root": "./media",
    "log_dir": "./logs",
    "poll_seconds": 5,
    "retry": {"max_attempts": 3, "backoff_seconds": 30},
    "downloader": {
        "enabled": True,
        "urls": [],
        "target_count": 10,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "max_video_uses": 3,
        "prune_over_target": True,
    },
    "stories": {
        "enabled": True,
        "pending_target": 4,
        "model": "gemini",
        "temperature": 0.9,
        "max_tokens": 1800,
        "topics": ["an unexpected encounter"],
        "prompts": {
            "male": "Write a compelling short story from a male perspective about {topic}.",
            "female": "Write a compelling short story from a female perspective about {topic}.",
        },
        "providers": {
            "story-local": {"type": "ollama", "base_url": "http://localhost:11434/v1", "model": "llama3.1"},
            "story-cloud": {"type": "openai_compatible", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "model": "gpt-4o-mini"},
            "gemini": {"type": "openai_compatible", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "api_key_env": "GEMINI_API_KEY", "model": "gemini-2.0-flash"},
        },
    },
    "tts": {
        "enabled": True,
        "mode": "kokoro",
        "male_voice": "am_michael",
        "female_voice": "af_heart",
        "speed": 1.0,
        "model": "tts-cloud",
        "providers": {"tts-cloud": {"type": "openai_compatible", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "model": "gpt-4o-mini-tts"}},
    },
    "subtitles": {
        "enabled": True,
        "mode": "faster_whisper",
        "model": "small",
        "device": "auto",
        "compute_type": "int8",
        "language": "en",
        "providers": {"subtitle-cloud": {"type": "openai_compatible", "base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY", "model": "whisper-1"}},
    },
    "composer": {"enabled": True, "ffmpeg": "ffmpeg", "output_width": 1080, "output_height": 1920, "fps": 30, "subtitle_style": "Default"},
    "tui": {"refresh_seconds": 1, "log_lines": 200},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path = "config.yaml", env_path: str | Path = ".env") -> dict[str, Any]:
    """Load non-secret settings from YAML; secret values are looked up by env name later."""
    path = Path(path)
    if Path(env_path).exists():
        load_dotenv(env_path, override=False)
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return deep_merge(DEFAULTS, raw)


def save_config(config: dict[str, Any], path: str | Path = "config.yaml") -> None:
    """Persist YAML atomically so a TUI edit cannot leave a truncated config."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def secret(name: str | None, env_path: str | Path = ".env") -> str:
    """Resolve a secret by its configured env-var name without placing it in YAML."""
    if not name:
        return ""
    values = dotenv_values(env_path)
    return str(os.environ.get(name) or values.get(name) or "")


def provider_config(config: dict[str, Any], section: str, name: str) -> dict[str, Any]:
    providers = config.get(section, {}).get("providers", {})
    value = providers.get(name, {})
    return value if isinstance(value, dict) else {}
