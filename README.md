# screen2tutorial

Turn a 5–10 minute English terminal or IDE recording into a step-by-step
Markdown tutorial. Speech transcription and screen OCR are aligned by time.
Each generated command is compared with both evidence sources; commands found
in neither are marked **UNVERIFIED**.

The supported scope is one English-speaking narrator, one terminal/IDE
recording, and Markdown output. The application has a Streamlit upload page and
the CLI `python -m pipeline.run path/to/video.mp4`.

## Install on Windows

1. Install Python 3.11 or 3.12 and create/activate a virtual environment:

   ```powershell
   py -3.11 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Install **ffmpeg** and make `ffmpeg.exe` available on `PATH`, or set
   `extract.ffmpeg_path` in `config.yaml` to its full path.
3. Install **Tesseract OCR** for Windows. If its executable is not on `PATH`, set
   `ocr.tesseract_cmd` in `config.yaml`, for example:
   `C:\Program Files\Tesseract-OCR\tesseract.exe`.
4. Run the UI with `streamlit run app.py`, or use the CLI command above.

The first run of faster-whisper may download its configured model. It runs on
CPU with the `base` model and int8 weights; allow enough disk space for that
model. ffmpeg and Tesseract are separate native programs and must be installed
outside pip.

## Configuration and model endpoint

All adjustable settings are in `config.yaml`: ffmpeg path, frame interval,
frame-difference threshold, Whisper model/runtime, Tesseract path, alignment
window size, fuzzy verification threshold, LLM endpoint/model, temperature,
offline mock mode, and disk caching.

By default, `llm.offline_mock: true` returns a canned empty-command step. This
lets the UI, CLI and tests run without credentials or network access. For real
generation, set `llm.offline_mock: false`, set `llm.base_url` and `llm.model` to
an OpenAI-compatible chat-completions endpoint and open-weight model, and
provide the key using the environment variable named by `llm.api_key_env`
(default `SCREEN2TUTORIAL_API_KEY`). The key can alternatively be supplied in
`llm.api_key` in the local `config.yaml`; never commit a real key. This project
does not call proprietary OpenAI or Anthropic models. The endpoint URL,
authentication requirements, model identifier, and compatibility are provider
configuration values; consult the chosen provider's documentation. A local
Ollama-compatible endpoint can be used by changing the config values.

## Pipeline and verification

1. `pipeline.extract` uses ffmpeg to create mono 16 kHz audio and PNG frames.
   Consecutive frames are downscaled to grayscale; frames with mean absolute
   difference at or below the configured threshold are dropped.
2. `pipeline.transcribe` runs faster-whisper on CPU. `pipeline.ocr` runs
   Tesseract on retained frames and removes blank/noise lines.
3. `pipeline.align` groups speech and unique OCR lines in fixed time windows.
4. `pipeline.write` requests strict JSON for one step per window. Invalid JSON
   is retried once, then the step falls back to its transcript and no commands.
5. `pipeline.verify` normalizes whitespace, quotes, and shell prompts, checks
   exact containment, then fuzzy partial similarity against each source.
6. `pipeline.render` writes numbered Markdown steps and a command count table.

Verification means only that a command resembles text captured in the speech or
on screen; it does not prove the command is correct or safe. Speech recognition
and OCR can make mistakes. Fuzzy matching can accept a near match or miss a
valid command, so review the output before publishing.

Each stage writes JSON cache data under `outputs/<video>-<hash>/`. The cache is
keyed by input content and relevant configuration. Delete that job directory to
force recomputation. `outputs/` and video files are ignored by Git.

## Tests

Run the fully offline unit suite with `python -m pytest`. Tests use generated
image fixtures and a mock LLM call; they do not invoke ffmpeg, Tesseract,
faster-whisper model downloads, or a network service.

## Design decisions

- Windows paths are accepted as ordinary config strings. ffmpeg is called with
  argument lists, not a shell, so spaces in paths are supported.
- Windows are fixed-duration buckets starting at multiples of the configured
  interval. Empty buckets are omitted; OCR text is de-duplicated case-insensitively
  within each bucket.
- The cache is per input content hash and stage settings, stored as readable
  JSON. A changed input naturally uses a new cache directory.
- Fuzzy matching uses RapidFuzz `partial_ratio` at the configured threshold.
  A command may be verified by speech, by OCR, or by both; no evidence means
  `unverified`.
- The default endpoint is a local OpenAI-compatible URL and offline mock mode is
  enabled. Provider-specific URL or key details are not assumed.

## Limitations

- The supported scope is short, single-speaker, English terminal/IDE footage.
- The tool does not identify speakers, execute commands, validate software
  behavior, or guarantee that OCR/transcription is accurate.
- The fixed 45-second window can combine unrelated actions or split one action.
- The default local LLM endpoint must be running and have the configured model
  available when offline mock mode is disabled.
- Performance depends strongly on CPU, video resolution, number of changed
  frames, Tesseract installation, and model endpoint. No representative
  5–10-minute recording was available in this build workspace, so per-stage
  runtime on the specified 8 GB/i3 target is not measured here.

## Future work

- Add a representative, redistributable sample video and a documented
  end-to-end benchmark on target hardware.
- Add finer-grained timestamp evidence for each extracted command.
- Improve window boundary selection and add a review/edit screen for corrections.
- Add an optional packaged Windows installer for ffmpeg and Tesseract.
