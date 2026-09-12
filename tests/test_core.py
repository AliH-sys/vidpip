from pathlib import Path

from storyforge.config import load_config, save_config
from storyforge.metadata import asset_metadata, fail_story, read_metadata, retry_failed
from storyforge.subtitles import ass_time, write_ass


def test_config_round_trip(tmp_path: Path):
    path = tmp_path / "config.yaml"
    save_config({"media_root": str(tmp_path / "media"), "poll_seconds": 2}, path)
    config = load_config(path, tmp_path / ".env")
    assert config["poll_seconds"] == 2
    assert "downloader" in config


def test_asset_metadata_sidecar(tmp_path: Path):
    asset = tmp_path / "voice.wav"
    asset.write_bytes(b"audio")
    asset_metadata(asset, "voice", status="unused")
    assert read_metadata(asset)["kind"] == "voice"
    assert (tmp_path / "voice.wav.json").exists()


def test_failure_retry_and_delete(tmp_path: Path):
    root = tmp_path / "media"
    folder = root / "stories" / "notFinished" / "story-1"
    folder.mkdir(parents=True)
    text = folder / "story.txt"
    text.write_text("story")
    asset_metadata(text, "story", retry_count=0)
    failed = fail_story(folder, "tts", "bad", 3)
    assert failed.parent.name == "failed"
    moved, deleted = retry_failed(root, 3)
    assert (moved, deleted) == (1, 0)
    failed = fail_story(root / "stories" / "notFinished" / "story-1", "tts", "bad", 3)
    assert failed.parent.name == "failed"
    moved, deleted = retry_failed(root, 3)
    assert (moved, deleted) == (0, 1)


def test_ass_output(tmp_path: Path):
    assert ass_time(65.5) == "0:01:05.50"
    output = tmp_path / "captions.ass"
    write_ass(output, [{"start": 0, "end": 1.5, "text": "Hello"}])
    assert "Dialogue: 0,0:00:00.00,0:00:01.50" in output.read_text()
