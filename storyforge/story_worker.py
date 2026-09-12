from __future__ import annotations

import random
import threading
import time
from pathlib import Path
from typing import Any

from .config import provider_config
from .logging_utils import get_logger
from .metadata import create_story, fail_story, story_files
from .providers import generate_story


class StoryWorker(threading.Thread):
    def __init__(self, config: dict[str, Any], gender: str, stop_event: threading.Event, module_event: threading.Event, dry_run: bool = False):
        super().__init__(name=f"story-{gender}", daemon=True)
        self.config, self.gender, self.stop_event, self.module_event, self.dry_run = config, gender, stop_event, module_event, dry_run
        self.log = get_logger(self.name)

    def pending(self, root: Path) -> int:
        count = 0
        for folder in story_files(root, "notFinished"):
            metadata = folder / "story.txt.json"
            if metadata.exists():
                import json
                try:
                    if json.loads(metadata.read_text(encoding="utf-8")).get("gender") == self.gender:
                        count += 1
                except json.JSONDecodeError:
                    pass
        return count

    def run(self) -> None:
        root = Path(self.config["media_root"])
        settings = self.config["stories"]
        provider_name = str(settings.get("model", ""))
        provider = provider_config(self.config, "stories", provider_name)
        while not self.stop_event.is_set():
            if not self.module_event.is_set():
                self.stop_event.wait(0.5)
                continue
            try:
                topic = random.choice(settings.get("topics") or ["an unexpected encounter"])
                prompt = str(settings.get("prompts", {}).get(self.gender, "Write a story about {topic}.")).format(topic=topic)
                if self.dry_run:
                    self.log.info("[dry-run] Would generate a %s story", self.gender)
                    self.stop_event.wait(1)
                    continue
                payload = generate_story(provider, prompt, self.gender, int(settings.get("max_tokens", 1800)), float(settings.get("temperature", 0.9)))
                payload["gender"] = self.gender
                folder = create_story(root, payload, prompt, provider_name)
                self.log.info("Generated %s story: %s", self.gender, folder.name)
            except Exception as exc:
                self.log.exception("Story generation failed (%s): %s", self.gender, exc)
                self.stop_event.wait(float(self.config.get("retry", {}).get("backoff_seconds", 30)))
