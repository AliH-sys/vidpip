from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

import urwid

from .config import save_config
from .logging_utils import MemoryLogHandler, get_logger
from .metadata import stats
from .pipeline import PipelineController
from .system_stats import get_system_stats

log = get_logger("tui")


class StoryForgeTUI:
    def __init__(self, config: dict[str, Any], config_path: str = "config.yaml", dry_run: bool = False):
        self.config = config
        self.config_path = config_path
        self.controller = PipelineController(config, dry_run=dry_run)
        self.log_handler: MemoryLogHandler | None = None
        self.log_text = urwid.Text("")
        self.stats_text = urwid.Text("")
        self.module_text = urwid.Text("")
        self.settings_text = urwid.Text("")
        self.loop: urwid.MainLoop | None = None
        self.body = urwid.Pile([])

    def attach_log_handler(self, handler: MemoryLogHandler) -> None:
        self.log_handler = handler

    def _button(self, label: str, callback: Callable[[Any], None]) -> urwid.Button:
        button = urwid.Button(label, on_press=callback)
        return urwid.AttrMap(button, None, focus_map="selected")

    def _toggle_module(self, name: str, _: Any = None) -> None:
        if self.controller.module_events[name].is_set():
            self.controller.stop_module(name)
            log.info("Stopped module %s", name)
        else:
            self.controller.start_module(name)
            log.info("Started module %s", name)
        self.refresh()

    def start_all(self, _: Any = None) -> None:
        self.controller.start_all()
        log.info("Started all modules")
        self.refresh()

    def stop_all(self, _: Any = None) -> None:
        self.controller.stop_all()
        log.info("Stopped all modules")
        self.refresh()

    def settings_form(self) -> urwid.Widget:
        fields: list[tuple[str, urwid.Edit, Callable[[str], None]]] = []
        def field(label: str, value: Any, setter: Callable[[str], None]) -> urwid.Edit:
            edit = urwid.Edit(f"{label}: ", str(value))
            fields.append((label, edit, setter))
            return edit
        widgets = [urwid.Text("Live settings (changes persist and apply to the next job)"), urwid.Divider()]
        widgets.append(field("Poll seconds", self.config.get("poll_seconds", 5), lambda v: self.config.__setitem__("poll_seconds", max(1, int(v)))))
        widgets.append(field("Retry max attempts", self.config["retry"].get("max_attempts", 3), lambda v: self.config["retry"].__setitem__("max_attempts", max(1, int(v)))))
        widgets.append(field("Background target", self.config["downloader"].get("target_count", 10), lambda v: self.config["downloader"].__setitem__("target_count", max(0, int(v)))))
        widgets.append(field("Max background uses", self.config["downloader"].get("max_video_uses", 3), lambda v: self.config["downloader"].__setitem__("max_video_uses", max(1, int(v)))))
        widgets.append(field("Pending stories/gender", self.config["stories"].get("pending_target", 4), lambda v: self.config["stories"].__setitem__("pending_target", max(1, int(v)))))
        widgets.append(field("Story model/provider", self.config["stories"].get("model", "story-local"), lambda v: self.config["stories"].__setitem__("model", v.strip())))
        widgets.append(field("TTS mode", self.config["tts"].get("mode", "kokoro"), lambda v: self.config["tts"].__setitem__("mode", v.strip())))
        widgets.append(field("Subtitle mode", self.config["subtitles"].get("mode", "faster_whisper"), lambda v: self.config["subtitles"].__setitem__("mode", v.strip())))
        widgets.append(field("Media root", self.config.get("media_root", "./media"), lambda v: self.config.__setitem__("media_root", v.strip())))
        def save(_: Any) -> None:
            try:
                for _, edit, setter in fields:
                    setter(edit.edit_text)
                save_config(self.config, self.config_path)
                log.info("Configuration saved")
                self.refresh()
            except (TypeError, ValueError) as exc:
                log.error("Settings not saved: %s", exc)
        widgets.append(urwid.Divider())
        widgets.append(self._button("Save settings", save))
        return urwid.ListBox(urwid.SimpleFocusListWalker(widgets))

    def yaml_editor(self) -> urwid.Widget:
        text = urwid.Edit("", json.dumps(self.config, indent=2))
        def save(_: Any) -> None:
            try:
                parsed = __import__("yaml").safe_load(text.edit_text)
                if not isinstance(parsed, dict):
                    raise ValueError("YAML root must be a mapping")
                self.config.clear()
                self.config.update(parsed)
                save_config(self.config, self.config_path)
                log.info("Raw YAML settings saved")
            except Exception as exc:
                log.error("Raw YAML not saved: %s", exc)
            self.refresh()
        return urwid.ListBox(urwid.SimpleFocusListWalker([urwid.Text("Advanced YAML view (JSON is valid YAML)"), urwid.Divider(), text, urwid.Divider(), self._button("Save YAML", save)]))

    def refresh(self, _loop: Any = None, _user_data: Any = None) -> None:
        counts = stats(Path(self.config["media_root"]))
        system = get_system_stats()
        status = self.controller.status()
        self.stats_text.set_text("  ".join(f"{key}: {value}" for key, value in counts.items()) + f"\nCPU {system['cpu']}%  RAM {system['memory']}%  Disk {system['disk']}%  Load {system['load']:.2f}")
        self.module_text.set_text("  ".join(f"{name}: {'RUNNING' if status.get(name) else 'STOPPED'}" for name in self.controller.MODULES))
        if self.log_handler:
            self.log_text.set_text("\n".join(self.log_handler.lines()[-int(self.config.get("tui", {}).get("log_lines", 200)):]))
        if self.loop:
            self.loop.set_alarm_in(float(self.config.get("tui", {}).get("refresh_seconds", 1)), self.refresh)

    def run(self) -> None:
        controls = [urwid.Text("STORYFORGE", align="center"), urwid.Divider(), self.stats_text, urwid.Divider(), self.module_text, urwid.Divider()]
        controls += [self._button("Start all", self.start_all), self._button("Stop all", self.stop_all)]
        controls += [self._button(f"Toggle {name}", lambda _, n=name: self._toggle_module(n)) for name in self.controller.MODULES]
        tabs = urwid.Pile([
            ("pack", urwid.Text("Controls")),
            ("pack", urwid.Divider()),
            ("weight", 1, urwid.ListBox(urwid.SimpleFocusListWalker(controls))),
        ])
        settings = self.settings_form()
        yaml_view = self.yaml_editor()
        logs = urwid.LineBox(urwid.Filler(self.log_text, valign="top"), title="Logs")
        columns = urwid.Columns([(34, urwid.LineBox(tabs, title="Modules")), (46, urwid.LineBox(settings, title="Settings")), urwid.LineBox(yaml_view, title="YAML")], dividechars=1)
        self.body = urwid.Pile([("weight", 3, columns), ("weight", 2, logs)])
        self.loop = urwid.MainLoop(
            urwid.AttrMap(self.body, "body"),
            [("body", "white", "black"), ("selected", "standout", "black")],
            unhandled_input=self.input_handler,
        )
        self.refresh()
        self.loop.run()

    def input_handler(self, key: str) -> None:
        if key in {"q", "Q"}:
            self.controller.stop_all()
            raise urwid.ExitMainLoop()
        if key == "s":
            self.start_all()
        elif key == "x":
            self.stop_all()
