from __future__ import annotations

import threading
import time
from typing import Any, Callable

from .composer import compose_once
from .downloader import download_once
from .logging_utils import get_logger
from .metadata import retry_failed
from .subtitles import process_subtitles_once
from .tts import process_tts_once
from .story_worker import StoryWorker

log = get_logger("pipeline")


class PipelineController:
    MODULES = ("downloader", "stories", "tts", "subtitles", "composer", "retry")

    def __init__(self, config: dict[str, Any], dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.stop_event = threading.Event()
        self.module_events = {name: threading.Event() for name in self.MODULES}
        for event in self.module_events.values():
            event.set()
        self.threads: dict[str, threading.Thread] = {}

    def _loop(self, name: str, function: Callable[[dict[str, Any], bool], int]) -> None:
        while not self.stop_event.is_set():
            if not self.module_events[name].is_set():
                self.stop_event.wait(0.5)
                continue
            try:
                function(self.config, self.dry_run)
            except Exception as exc:
                log.exception("Module %s crashed: %s", name, exc)
            self.stop_event.wait(float(self.config.get("poll_seconds", 5)))

    def start_module(self, name: str) -> None:
        if name not in self.module_events:
            raise ValueError(name)
        self.module_events[name].set()
        if name == "stories":
            if "story-male" not in self.threads or not self.threads["story-male"].is_alive():
                for gender in ("male", "female"):
                    thread = StoryWorker(self.config, gender, self.stop_event, self.module_events["stories"], self.dry_run)
                    self.threads[f"story-{gender}"] = thread
                    thread.start()
            return
        if name in self.threads and self.threads[name].is_alive():
            return
        funcs = {"downloader": download_once, "tts": process_tts_once, "subtitles": process_subtitles_once, "composer": compose_once}
        if name == "retry":
            def retry(config: dict[str, Any], _: bool) -> int:
                retried, deleted = retry_failed(__import__("pathlib").Path(config["media_root"]), int(config.get("retry", {}).get("max_attempts", 3)))
                if retried or deleted:
                    log.info("Retry scan: requeued=%s deleted=%s", retried, deleted)
                return retried
            funcs[name] = retry
        thread = threading.Thread(target=self._loop, args=(name, funcs[name]), name=name, daemon=True)
        self.threads[name] = thread
        thread.start()

    def stop_module(self, name: str) -> None:
        if name in self.module_events:
            self.module_events[name].clear()

    def start_all(self) -> None:
        for name in self.MODULES:
            self.start_module(name)

    def stop_all(self) -> None:
        self.stop_event.set()
        for event in self.module_events.values():
            event.clear()
        for thread in self.threads.values():
            thread.join(timeout=2)

    def status(self) -> dict[str, bool]:
        return {name: self.module_events[name].is_set() and any(thread.is_alive() for key, thread in self.threads.items() if key == name or (name == "stories" and key.startswith("story-"))) for name in self.MODULES}
