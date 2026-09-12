from __future__ import annotations

import logging
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock


class MemoryLogHandler(logging.Handler):
    def __init__(self, maxlen: int = 200):
        super().__init__()
        self.records: deque[str] = deque(maxlen=maxlen)
        self._lock = Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            with self._lock:
                self.records.append(line)
        except Exception:
            self.handleError(record)

    def lines(self) -> list[str]:
        with self._lock:
            return list(self.records)


def configure_logging(log_dir: str | Path, max_lines: int = 200) -> MemoryLogHandler:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("storyforge")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    file_handler = RotatingFileHandler(Path(log_dir) / "storyforge.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    memory_handler = MemoryLogHandler(max_lines)
    memory_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(memory_handler)
    return memory_handler


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"storyforge.{name}")
