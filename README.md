# Timbre

**A local voice cloning studio.** Give it 10–30 seconds of someone speaking, type a script, and get back natural speech in that voice, with subtitles. Everything runs on your own machine.

![Timbre studio](docs/screenshot.png)

## Features

- **Zero-shot cloning** with [XTTS-v2](https://huggingface.co/coqui/XTTS-v2): no training, just a short reference clip
- **Upload or record** reference voices in the browser, with automatic cleanup (silence trimming, loudness normalization, resampling)
- **Voice library**: save voices once and reuse them
- **One take or a whole script**: batch mode turns each line into its own clip, plus one merged file
- **Subtitles**: every take comes with a timed `.srt` file
- **17 languages**, adjustable speed
- **Swappable engines**: a clean `Engine` interface, plus a demo engine that runs with no model or GPU
- **Web studio, CLI and JSON API**

## Quick start

### What you need

- **Python 3.12** exactly. Newer versions don't work yet: the PyTorch builds for Python 3.13+ need torchcodec and FFmpeg libraries to read audio, which the voice model can't load without.
- About **3 GB** of free space and a decent internet connection: ~1 GB of packages plus the ~1.8 GB voice model on first start.
- Optional: an **NVIDIA GPU**. Without one, Timbre runs on your CPU and takes a few seconds of work per second of speech.
- Optional: [ffmpeg](https://ffmpeg.org/download.html) on PATH, only for unusual audio formats. Recordings, WAV, MP3 and M4A work without it.

### Windows

1. Install [Python 3.12](https://www.python.org/downloads/release/python-31210/) (tick "Add python.exe to PATH").
2. Download this repository (**Code → Download ZIP**, then unzip) or `git clone` it.
3. Double-click **`setup.bat`**. For an NVIDIA GPU, run `setup.bat cuda` from a terminal instead.
4. Double-click **`run-timbre.bat`**. On the first start, type `y` to accept the model license when asked.

Your browser opens http://127.0.0.1:7860 when the studio is ready. Keep the black window open while you use it.

`run-demo.bat` starts the studio with a placeholder engine instead, which needs no model: handy for trying the interface.

### macOS / Linux

```bash
git clone https://github.com/earldavemurillo123-create/timbre.git
cd timbre
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python cli.py serve            # or: python cli.py --engine demo serve
```

Open **http://127.0.0.1:7860**. The first start downloads the XTTS-v2 weights and asks you to accept the model license; set `COQUI_TOS_AGREED=1` to accept it in advance. On Linux, PyPI's `torch` already includes CUDA support for NVIDIA GPUs.

### Troubleshooting

| Problem | Fix |
|---|---|
| `torchcodec library is required` | You're on Python 3.13+ or a newer PyTorch. Use Python 3.12 and `requirements.txt`. |
| `No module named 'six'` | Run `pip install -r requirements.txt` again; it includes it. |
| Browser shows "can't be reached" | The model is still loading. Wait a minute and refresh. |
| Generation is slow | Expected on CPU. An NVIDIA GPU with `setup.bat cuda` is much faster. |
| A clip in an unusual format won't save | The browser converts recordings, MP3 and M4A to WAV automatically. For other formats, convert to WAV first or install ffmpeg. |

## Command line

```bash
python cli.py voices add "Narrator" my-voice.wav --consent
python cli.py voices list
python cli.py speak narrator-1a2b3c "Hello from Timbre." -o hello.wav
python cli.py batch narrator-1a2b3c examples/script.txt --language en --speed 1.1
```

Generated takes are saved in `data/takes/<take-id>/` as `take.wav`, `take.srt` and (for scripts) `line-1.wav`, `line-2.wav`, …

## Tips for a good clone

- 10–30 seconds of **one speaker**, no background music, little room echo
- Natural sentences in a normal speaking voice. Expressive references give expressive output.
- The reference language doesn't have to match the output language, but matching it sounds best.

## How it works

```
reference clip ──► cleanup ──► speaker embedding ─┐
                                                  ├──► XTTS-v2 ──► audio per sentence ──► join + pauses ──► take.wav + take.srt
script ──► sentence splitting ────────────────────┘
```

| Path | Purpose |
|---|---|
| `timbre/audio.py` | Loading (ffmpeg fallback), trimming, normalizing, WAV writing with a "synthetic" tag |
| `timbre/text.py` | Sentence splitting, chunking, script parsing, SRT building |
| `timbre/engines/` | `Engine` interface, XTTS-v2 and demo engines |
| `timbre/voices.py` | Saved voice library |
| `timbre/studio.py` | Generation service shared by the server and CLI |
| `timbre/server.py` | FastAPI app: JSON API + static web UI |
| `web/` | The studio interface (plain HTML/CSS/JS, no build step) |

### Adding another model

Subclass `Engine` in `timbre/engines/`, implement `load()` and `synthesize()`, then register it in `ENGINES` in `timbre/engines/__init__.py`. Start it with `--engine yourname`.

### API

| Method | Route | Description |
|---|---|---|
| `GET` | `/api/status` | Engine name, device, languages |
| `GET` / `POST` | `/api/voices` | List voices / add one (multipart: `name`, `consent`, `file`) |
| `PATCH` / `DELETE` | `/api/voices/{id}` | Rename / delete |
| `POST` | `/api/speak` | `{voice_id, text, language, speed}` → take |
| `POST` | `/api/batch` | `{voice_id, script, language, speed}` → take |
| `GET` | `/api/takes` | Recent takes |
| `GET` | `/api/takes/{id}/{file}` | Download audio or subtitles (`?download=true`) |

Interactive docs are at `/docs` while the server is running.

## Configuration

| Variable | Default | |
|---|---|---|
| `TIMBRE_ENGINE` | `xtts` | `xtts` or `demo` |
| `TIMBRE_DEVICE` | `auto` | `auto`, `cuda` or `cpu` |
| `TIMBRE_DATA_DIR` | `./data` | Where voices and takes are stored |

## Running tests

```bash
pytest
```

The tests use the demo engine, so they run in about a second without a GPU.

## Responsible use

Voice cloning can be misused to impersonate people. Timbre is built for your own voice, voices you have explicit permission to use, and fictional characters you voice yourself.

- Saving a voice requires confirming you have the speaker's permission.
- Every generated WAV carries an embedded comment marking it as synthetic speech.
- Don't use Timbre to deceive, defraud or harass anyone, or to create content that a person hasn't agreed to.

## License

Timbre's code is MIT licensed. The XTTS-v2 model weights are under the [Coqui Public Model License](https://coqui.ai/cpml), which **does not allow commercial use**. Check the license of any model you plug in.

## Credits

- [XTTS-v2](https://huggingface.co/coqui/XTTS-v2) by Coqui, maintained in the [coqui-tts](https://github.com/idiap/coqui-ai-TTS) fork
- Interface typeface: [Bricolage Grotesque](https://fonts.google.com/specimen/Bricolage+Grotesque)
