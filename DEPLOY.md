# Deployment runbook

## Direct Linux install

```bash
sudo apt-get install ffmpeg python3.11 python3.11-venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m storyforge.cli init
python -m storyforge.cli doctor
```

Set `media_root` and `log_dir` in `config.yaml`, populate `downloader.urls`, select providers/models, and then run `python -m storyforge.cli tui`.

## systemd

The repository includes a service template at `deploy/storyforge.service`. Copy it to `/etc/systemd/system/storyforge.service`, change `/opt/storyforge` in `WorkingDirectory` and `ExecStart` if needed, then enable it:

```bash
sudo cp deploy/storyforge.service /etc/systemd/system/storyforge.service
sudo systemctl daemon-reload
sudo systemctl enable --now storyforge
journalctl -u storyforge -f
```

This starts the workers automatically when the host reaches the multi-user target and restarts them after unexpected exits. Use the TUI for interactive control. The CLI `run` command is intended for a supervisor. Stop workers before changing model files or removing media. Config writes are atomic, and workers claim story folders with lock directories so multiple processes do not process the same asset.

## Provider setup

- **Ollama:** run Ollama locally and set `stories.model` to a provider with `type: ollama`.
- **OpenAI-compatible cloud:** select a profile and set its `api_key_env` to one of the `.env` names. Profiles for Gemini, Mistral, Groq, NVIDIA NIM, and Z.ai are included in `config.yaml`.
- **Kokoro/Chatterbox:** install the selected optional package and its model dependencies; set `tts.mode`.
- **faster-whisper:** select `subtitles.mode: faster_whisper`, set model/device/compute type, and run doctor.

Do not place secret values in YAML, logs, story prompts, or metadata. `.env` is ignored by git.
