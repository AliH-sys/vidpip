from __future__ import annotations

import json
import re
from typing import Any

from .config import secret


class ProviderError(RuntimeError):
    pass


def openai_client(provider: dict[str, Any]):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ProviderError("The openai package is not installed") from exc
    api_key = secret(provider.get("api_key_env")) or "ollama"
    return OpenAI(api_key=api_key, base_url=provider.get("base_url"))


def extract_json(value: str) -> dict[str, Any]:
    value = value.strip()
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", value, re.DOTALL)
        if not match:
            raise ProviderError("LLM response was not valid JSON")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise ProviderError("LLM response contained malformed JSON") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("LLM response must be a JSON object")
    required = ("title", "story", "description", "tags", "gender")
    missing = [key for key in required if not parsed.get(key)]
    if missing or parsed.get("gender") not in {"male", "female"} or not isinstance(parsed.get("tags"), list):
        raise ProviderError(f"LLM JSON is missing or has invalid fields: {', '.join(missing) or 'schema'}")
    return parsed


def generate_story(provider: dict[str, Any], prompt: str, gender: str, max_tokens: int, temperature: float) -> dict[str, Any]:
    client = openai_client(provider)
    model = provider.get("model")
    system = ("Return ONLY a JSON object with exactly these fields: title, story, description, tags, gender. "
              f"The gender field must be '{gender}'. Do not use markdown fences.")
    response = client.chat.completions.create(model=model, temperature=temperature, max_tokens=max_tokens, response_format={"type": "json_object"}, messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    content = response.choices[0].message.content or ""
    return extract_json(content)


def synthesize_cloud(provider: dict[str, Any], text: str, voice: str, output_path: str) -> None:
    client = openai_client(provider)
    response = client.audio.speech.create(model=provider.get("model", "gpt-4o-mini-tts"), voice=voice, input=text, response_format="wav", speed=float(provider.get("speed", 1.0)))
    response.write_to_file(output_path)


def transcribe_cloud(provider: dict[str, Any], audio_path: str, language: str | None = None) -> list[dict[str, Any]]:
    client = openai_client(provider)
    with open(audio_path, "rb") as audio:
        result = client.audio.transcriptions.create(model=provider.get("model", "whisper-1"), file=audio, response_format="verbose_json", timestamp_granularities=["segment"], language=language)
    return [{"start": float(item.start), "end": float(item.end), "text": item.text} for item in (getattr(result, "segments", None) or [])]
