# tts-hub

A small, pluggable, self-hosted **text-to-speech server**. Payload in → audio out.
Ships with **Kokoro-82M** (English + Hindi and more) and is built so you can drop in
additional TTS models later without touching the API or the tester.

## Why

A model-evaluation + serving harness for picking a fast, self-hostable TTS for a
voice-agent use case (English + Indic). Kokoro is the first engine; Piper, AI4Bharat,
etc. can be added as new engines behind the same interface.

## Quick start

One command takes a fresh checkout to "ready to run" — it installs `uv` and
`espeak-ng` if missing, installs the Python deps, writes `.env`, and downloads the
Kokoro weights:

```bash
./setup.sh        # or: ./run.sh setup
./run.sh dev      # or: uv run tts-hub
```

Then open the tester at **`http://localhost:8000/test.html`**.

`setup.sh` flags:

| Flag | Effect |
|---|---|
| `--skip-model` | Don't pre-download weights (fetched lazily on first run) |
| `--device <cpu\|mps\|cuda>` | Force `KOKORO_DEVICE` in `.env` (default: `mps` on Apple Silicon, else `cpu`) |
| `--no-dev` | Runtime deps only (skip dev extras + smoke test) |
| `--skip-tests` | Skip the final `pytest` smoke check |

### Tasks (`./run.sh`)

`run.sh` is a plain shell task runner — no extra tooling needed:

| Command | Runs |
|---|---|
| `./run.sh setup` | full end-to-end setup (delegates to `setup.sh`) |
| `./run.sh dev` | start with auto-reload (`RELOAD=true uv run tts-hub`) |
| `./run.sh start` | start without auto-reload (`RELOAD=false uv run tts-hub`) |
| `./run.sh serve` | raw uvicorn (`uv run uvicorn app.main:app --reload`) |
| `./run.sh download-model` | pre-download the Kokoro weights |
| `./run.sh test` | `uv run pytest` |
| `./run.sh clean` | remove `.venv`, caches, and `__pycache__` |

## Install (manual)

Prefer `./setup.sh` above. To do it by hand with [`uv`](https://docs.astral.sh/uv/):

```bash
cd ~/repository/tts-hub
uv sync                      # or: pip install -e ".[dev]"
```

Kokoro uses `espeak-ng` as a phonemizer fallback for some languages:

```bash
brew install espeak-ng       # macOS
# sudo apt-get install espeak-ng   # Debian/Ubuntu
```

First run downloads the Kokoro weights (~330 MB) from Hugging Face. To fetch them
ahead of time: `./run.sh download-model`.

## Run

```bash
uv run tts-hub
```

This reads `HOST`, `PORT`, `RELOAD`, and `KOKORO_DEVICE` from `.env` (defaults to
`http://0.0.0.0:8000` with auto-reload). To override the port ad hoc, or to use the
raw uvicorn CLI instead:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

On Apple Silicon, set `KOKORO_DEVICE=mps` in `.env` for GPU acceleration; on a CPU-only
VM leave it `cpu`.

## Test it

With the server running, open **`http://localhost:<PORT>/test.html`** (the page
auto-detects the port when served this way). Pick a model, voice, and language, type
text, and hit Generate. You can also double-click `test.html` (`file://`) and set the
API base field manually — CORS is open so that works too.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness + default model |
| GET | `/models` | Registered engines, their languages and voice counts |
| GET | `/voices?model=kokoro` | Voice catalog for a model |
| POST | `/tts` | Synthesize speech (audio streams per segment; or JSON) |
| GET | `/tts?text=...&voice=...` | Streaming synthesis for an `<audio>` element |

**Streaming:** audio responses stream per synthesis segment — a WAV header is sent
first, then PCM frames as each segment is produced, so playback can start before the
whole clip is done (low time-to-first-audio). Kokoro's pipeline yields per sentence/
chunk, mirroring how a real voice agent consumes TTS. The `response: "json"` path
buffers the full clip (it can't stream).

`POST /tts` body:

```json
{
  "text": "Hello world",
  "model": "kokoro",
  "voice": "af_heart",
  "language": "en",
  "speed": 1.0,
  "response": "audio"
}
```

- `response: "audio"` (default) streams `audio/wav` bytes.
- `response: "json"` returns `{audio_base64, sample_rate, format, duration_secs, model, voice}`.
- `voice`/`language` are optional; omit `voice` to use the engine default. For Kokoro,
  voice ids encode language + gender (`af_*`/`am_*` US English, `bf_*`/`bm_*` UK English,
  `hf_*`/`hm_*` Hindi).

Examples:

```bash
curl localhost:8000/models
curl "localhost:8000/voices?model=kokoro"

# raw WAV
curl -X POST localhost:8000/tts \
  -H 'content-type: application/json' \
  -d '{"text":"hello world"}' --output out.wav

# Hindi voice
curl -X POST localhost:8000/tts \
  -H 'content-type: application/json' \
  -d '{"text":"नमस्ते","voice":"hf_alpha"}' --output hi.wav

# JSON + base64
curl -X POST localhost:8000/tts \
  -H 'content-type: application/json' \
  -d '{"text":"hello","response":"json"}'
```

## Adding a new model

1. Create `app/engines/your_engine.py` and subclass `TTSEngine` (`app/engines/base.py`),
   implementing `load`, `list_voices`, `languages`, and `synthesize`
   (return `(float32 mono ndarray, sample_rate)`).
2. Register it in `app/bootstrap.py`:

   ```python
   from app.engines.your_engine import YourEngine
   # inside register_default_engines():
   register(YourEngine())
   ```

That's it — `/models`, `/voices`, `/tts`, and `test.html` pick it up automatically.

## Tests

```bash
uv run pytest
```

Tests use a fake engine, so they run fast and offline. The Kokoro engine is verified
manually via `test.html` / the curl examples above.

## Layout

```
app/
  main.py        FastAPI app (CORS, lifespan warmup, serves test.html)
  config.py      env-backed settings
  schemas.py     TTSRequest / VoiceInfo / ModelInfo / JSON response
  registry.py    name -> engine, lazy load
  bootstrap.py   registers the built-in engines
  audio.py       float32 -> WAV bytes
  engines/
    base.py        TTSEngine ABC (the extension point)
    kokoro_engine.py
  api/routes.py  /health /models /voices /tts
setup.sh         end-to-end setup (uv, espeak-ng, deps, .env, weights)
run.sh           task runner (setup / dev / start / serve / test / clean)
test.html        standalone tester
```
