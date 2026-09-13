from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

from .composer import compose_once
from .config import load_config, save_config
from .doctor import run_doctor
from .downloader import download_once
from .logging_utils import configure_logging, get_logger
from .media import ensure_media_tree
from .pipeline import PipelineController
from .subtitles import process_subtitles_once
from .tts import process_tts_once


def main() -> int:
    parser = argparse.ArgumentParser(prog="storyforge", description="TUI-controlled story-to-video pipeline")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--env", default=".env")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("tui", help="open the full-screen monitor and controller")
    sub.add_parser("doctor", help="check dependencies and local prerequisites")
    sub.add_parser("init", help="create the media tree and default config")
    run = sub.add_parser("run", help="run all independent workers until interrupted")
    run.add_argument("--dry-run", action="store_true", help="log one simulated cycle without downloads/models/ffmpeg")
    once = sub.add_parser("once", help="run one scan of every non-story stage")
    once.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    config = load_config(args.config, args.env)
    configure_logging(config.get("log_dir", "./logs"), int(config.get("tui", {}).get("log_lines", 200)))
    root = Path(config["media_root"])
    ensure_media_tree(root)
    if args.command == "init":
        save_config(config, args.config)
        print(f"Initialized {root} and {args.config}. Copy .env.example to .env for secrets.")
        return 0
    if args.command == "doctor":
        return run_doctor(config)
    if args.command == "once":
        dry = bool(args.dry_run)
        download_once(config, dry)
        controller = PipelineController(config, dry_run=dry)
        process_tts_once(config, dry)
        process_subtitles_once(config, dry)
        compose_once(config, dry)
        return 0
    if args.command == "run":
        controller = PipelineController(config, dry_run=bool(args.dry_run))
        controller.start_all()
        print("StoryForge workers running. Press Ctrl-C to stop.")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            controller.stop_all()
        return 0
    try:
        from .tui import StoryForgeTUI
    except ModuleNotFoundError as exc:
        if exc.name != "urwid":
            raise
        print(
            "The StoryForge TUI requires 'urwid'. Activate the project environment "
            "and install dependencies with: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    tui = StoryForgeTUI(config, args.config)
    # configure_logging returns the handler; recreate it only when TUI is selected is not necessary,
    # so attach the handler from the root logger.
    import logging
    tui.attach_log_handler(next((h for h in logging.getLogger("storyforge").handlers if hasattr(h, "lines")), None))
    try:
        tui.run()
    except KeyboardInterrupt:
        tui.controller.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
