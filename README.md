# StoryForge TUI

StoryForge is a Linux/Python 3.11+ full-screen Urwid application that turns generated stories into narrated, subtitled videos. Every stage is an independent file-discovering worker, so stages can be started, stopped, or run separately.

## Pipeline

1. **Downloader** uses `yt-dlp` to fill the configured exact-size background-video pool from individual URLs.
2. **Stories** runs one male-perspective and one female-perspective worker in parallel. Providers use Ollama or OpenAI-compatible endpoints, including Gemini, Mistral, Groq, NVIDIA NIM, and Z.ai profiles.
3. **TTS** discovers story text files and creates `voice.wav` using Kokoro, Chatterbox, or an OpenAI-compatible speech API.
4. **Subtitles** discovers audio and creates styled `subtitles.ass` with faster-whisper or a cloud Whisper-compatible endpoint.
5. **Composer** loops/trims a background to the voice duration, burns ASS subtitles, and writes `video.mp4` with ffmpeg.
6. **Retry** moves failed stories back to `notFinished`; after `max_attempts` they are deleted. Stories are generated continuously until the stories module is stopped.

## Installation

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m storyforge.cli init
```

Install ffmpeg from your Linux distribution. Install and run Ollama for local stories, or configure a cloud profile and its API key in `.env`. Install Kokoro or Chatterbox separately when selecting those TTS modes; these packages may require a suitable PyTorch/CUDA setup.

## Configuration

`config.yaml` contains all non-secret, configurable settings: paths, URLs, provider profiles, models, prompts, voices, worker intervals, quotas, formats, ffmpeg, retries, and TUI behavior. `.env` contains secret values only. Provider profiles reference secrets by `api_key_env`; no key is written to YAML.

The TUI's **Settings** pane edits common typed values. The **YAML** pane accepts YAML (JSON is valid YAML) for advanced editing. Saving is atomic and changes affect the next job; active jobs are not interrupted.

## Media layout

```text
media/
├── background_videos/
│   ├── video.mp4
│   └── video.mp4.json
├── stories/
│   ├── notFinished/<story-id>/
│   │   ├── story.txt
│   │   ├── story.txt.json
│   │   ├── voice.wav
│   │   ├── voice.wav.json
│   │   ├── subtitles.ass
│   │   ├── subtitles.ass.json
│   │   └── (story, voice, and subtitle assets with JSON sidecars)
│   ├── finished/<story-id>/
│   └── failed/<story-id>/
└── story-id.mp4
```

The final video is produced at `media/story-id.mp4`, while the completed story assets are moved to `media/stories/finished/<story-id>`. Every downloaded/generated asset has a JSON sidecar containing status, provenance, timestamps, and relevant settings.

Background videos track `use_count`. Once `max_video_uses` is reached, the source video and sidecar are deleted after the current composition. If the pool is over target, videos at the use limit are pruned first, followed by oldest videos.

## Commands

```bash
python -m storyforge.cli tui                 # full-screen TUI
python -m storyforge.cli run                 # all workers until Ctrl-C
python -m storyforge.cli run --dry-run       # simulated continuous workers
python -m storyforge.cli once --dry-run      # one simulated stage scan
python -m storyforge.cli doctor              # dependencies and ffmpeg checks
./scripts/test.sh
```

TUI controls: `s` starts all modules, `x` stops all modules, and `q` exits. Buttons independently toggle downloader, stories, TTS, subtitles, composer, and retry. The dashboard shows counts, CPU/RAM/disk/load, worker status, and rotating logs.

## Testing and deployment

The test suite covers YAML round trips, sidecar metadata, failure/retry/deletion, and ASS generation. `doctor` validates local prerequisites without invoking providers. For a long-running deployment, use a systemd service or a terminal multiplexer; do not put `.env` under source control. A sample systemd unit:

```ini
[Unit]
Description=StoryForge workers
After=network-online.target

[Service]
WorkingDirectory=/opt/storyforge
ExecStart=/opt/storyforge/.venv/bin/python -m storyforge.cli run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

This project intentionally does not auto-download models or contact cloud providers. Configure credentials, models, and local services before enabling those modules.
