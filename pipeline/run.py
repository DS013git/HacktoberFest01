"""Orchestrate cached pipeline stages and provide the command-line entry point."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from pipeline.align import Window, align_windows, windows_to_json
from pipeline.extract import dedupe_frames, extract_media
from pipeline.ocr import OCRFrame, ocr_frames, ocr_to_json
from pipeline.render import render_markdown
from pipeline.transcribe import Segment, segments_to_json, transcribe_audio
from pipeline.verify import CheckedCommand, verify_commands
from pipeline.write import Step, step_to_json, write_step


LOGGER = logging.getLogger("screen2tutorial")


@dataclass(frozen=True)
class RunResult:
    """Final tutorial output, its path, and per-stage durations."""

    markdown: str
    output_path: Path
    timings: dict[str, float]


def load_config(config_path: Path) -> dict[str, Any]:
    """Load YAML configuration and validate the top-level mapping."""
    try:
        with Path(config_path).open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:
        raise ValueError(f"Config file not found: {config_path}") from exc
    if not isinstance(config, dict):
        raise ValueError(f"Config must contain a YAML mapping: {config_path}")
    return config


def _json_default(value: Any) -> Any:
    """Serialize path-like and dataclass-like cache values."""
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return value.__dict__
    raise TypeError(f"Unsupported cache value: {type(value).__name__}")


def _signature(payload: Any) -> str:
    """Return a stable digest for a JSON-compatible cache signature."""
    blob = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _file_sha256(path: Path) -> str:
    """Hash an input file in chunks to keep memory use bounded."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_cache(cache_path: Path, signature: str, enabled: bool) -> Any | None:
    """Read a stage cache when its signature still matches."""
    if not enabled or not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload.get("value") if payload.get("signature") == signature else None


def _write_cache(cache_path: Path, signature: str, value: Any, enabled: bool) -> None:
    """Persist one JSON stage output with its cache signature."""
    if enabled:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"signature": signature, "value": value}, indent=2, default=_json_default),
            encoding="utf-8",
        )


def _timed(name: str, callback: Callable[[], Any], timings: dict[str, float]) -> Any:
    """Run one pipeline stage, log elapsed time, and preserve its return value."""
    started = time.perf_counter()
    result = callback()
    elapsed = time.perf_counter() - started
    timings[name] = elapsed
    LOGGER.info("Stage %s took %.2f seconds", name, elapsed)
    return result


def _cache_hit(name: str, timings: dict[str, float]) -> None:
    """Record and log zero processing time when a stage result is cached."""
    timings[name] = 0.0
    LOGGER.info("Stage %s took %.2f seconds (cache hit)", name, timings[name])


def run_pipeline(
    video_path: Path,
    config_path: Path | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> RunResult:
    """Process a recording into verified Markdown using signed JSON stage caches."""
    source = Path(video_path).resolve()
    if not source.is_file():
        raise ValueError(f"Unreadable video: file does not exist: {source}")
    actual_config = Path(config_path or Path(__file__).parents[1] / "config.yaml").resolve()
    config = load_config(actual_config)
    cache_enabled = bool(config.get("cache", {}).get("enabled", True))
    config_root = actual_config.parent
    media_hash = _file_sha256(source)
    output_root = Path(config.get("extract", {}).get("output_dir", "outputs"))
    if not output_root.is_absolute():
        output_root = config_root / output_root
    job_dir = output_root / f"{source.stem}-{media_hash[:10]}"
    job_dir.mkdir(parents=True, exist_ok=True)
    timings: dict[str, float] = {}

    def report(stage: str) -> None:
        """Notify an optional UI callback about the active pipeline stage."""
        if progress_callback:
            progress_callback(stage)

    report("Extracting audio and frames")
    extract_signature = _signature([media_hash, config.get("extract", {}), config.get("dedupe", {})])
    extract_cache = job_dir / "extract.json"
    extract_value = _read_cache(extract_cache, extract_signature, cache_enabled)

    def do_extract() -> dict[str, Any]:
        """Extract media and cache paths to deduplicated frames."""
        audio, frames = extract_media(
            source, job_dir / "media",
            int(config.get("extract", {}).get("frame_interval_seconds", 2)),
            str(config.get("extract", {}).get("ffmpeg_path", "ffmpeg")),
        )
        kept = dedupe_frames(frames, float(config.get("dedupe", {}).get("difference_threshold", 8.0)))
        return {"audio": str(audio), "frames": [[stamp, str(path)] for stamp, path in kept]}

    extracted = extract_value if extract_value is not None else _timed("extract+dedupe", do_extract, timings)
    if extract_value is not None:
        _cache_hit("extract+dedupe", timings)
    _write_cache(extract_cache, extract_signature, extracted, cache_enabled)
    audio_path = Path(extracted["audio"])
    frames = [(float(stamp), Path(path)) for stamp, path in extracted["frames"]]

    report("Transcribing speech")
    transcribe_signature = _signature([media_hash, config.get("transcribe", {})])
    transcript_cache = job_dir / "transcribe.json"
    transcript_value = _read_cache(transcript_cache, transcribe_signature, cache_enabled)

    def do_transcribe() -> list[dict[str, Any]]:
        """Transcribe extracted audio and return cacheable segments."""
        segments = transcribe_audio(
            audio_path,
            str(config.get("transcribe", {}).get("model", "base")),
            str(config.get("transcribe", {}).get("compute_type", "int8")),
            str(config.get("transcribe", {}).get("device", "cpu")),
            str(config.get("transcribe", {}).get("language", "en")),
        )
        return segments_to_json(segments)

    transcript_data = transcript_value if transcript_value is not None else _timed("transcribe", do_transcribe, timings)
    if transcript_value is not None:
        _cache_hit("transcribe", timings)
    _write_cache(transcript_cache, transcribe_signature, transcript_data, cache_enabled)
    segments = [Segment(float(row["start"]), float(row["end"]), str(row["text"])) for row in transcript_data]

    report("Reading screen text")
    ocr_signature = _signature([media_hash, config.get("extract", {}), config.get("dedupe", {}), config.get("ocr", {})])
    ocr_cache = job_dir / "ocr.json"
    ocr_value = _read_cache(ocr_cache, ocr_signature, cache_enabled)

    def do_ocr() -> list[dict[str, Any]]:
        """Recognize screen text and return cacheable OCR rows."""
        return ocr_to_json(ocr_frames(
            frames, str(config.get("ocr", {}).get("tesseract_cmd", ""))
        ))

    ocr_data = ocr_value if ocr_value is not None else _timed("ocr", do_ocr, timings)
    if ocr_value is not None:
        _cache_hit("ocr", timings)
    _write_cache(ocr_cache, ocr_signature, ocr_data, cache_enabled)
    screen = [OCRFrame(float(row["timestamp"]), str(row["text"])) for row in ocr_data]

    report("Aligning transcript and screen text")
    align_signature = _signature([segments_to_json(segments), ocr_to_json(screen), config.get("align", {})])
    align_cache = job_dir / "align.json"
    align_value = _read_cache(align_cache, align_signature, cache_enabled)

    def do_align() -> list[dict[str, Any]]:
        """Align speech and OCR into fixed windows."""
        return windows_to_json(align_windows(segments, screen, int(config.get("align", {}).get("window_seconds", 45))))

    aligned_data = align_value if align_value is not None else _timed("align", do_align, timings)
    if align_value is not None:
        _cache_hit("align", timings)
    _write_cache(align_cache, align_signature, aligned_data, cache_enabled)
    windows = [Window(float(row["start"]), float(row["end"]), str(row["transcript"]), str(row["screen_text"])) for row in aligned_data]

    report("Writing tutorial steps")
    llm_config = config.get("llm", {})
    write_signature = _signature([aligned_data, {key: value for key, value in llm_config.items() if key not in {"api_key"}}])
    write_cache = job_dir / "write.json"
    write_value = _read_cache(write_cache, write_signature, cache_enabled)

    def do_write() -> list[dict[str, Any]]:
        """Generate one JSON tutorial step per window."""
        return [step_to_json(write_step(window, llm_config)) for window in windows]

    steps_data = write_value if write_value is not None else _timed("write", do_write, timings)
    if write_value is not None:
        _cache_hit("write", timings)
    _write_cache(write_cache, write_signature, steps_data, cache_enabled)
    steps = [Step(str(row["title"]), str(row["explanation"]), list(row["commands"])) for row in steps_data]

    report("Verifying commands")
    verify_signature = _signature([steps_data, [window.transcript for window in windows], [window.screen_text for window in windows], config.get("verify", {})])
    verify_cache = job_dir / "verify.json"
    verify_value = _read_cache(verify_cache, verify_signature, cache_enabled)

    def do_verify() -> list[list[dict[str, str]]]:
        """Verify each step's commands against its corresponding evidence."""
        return [[{"command": item.command, "status": item.status} for item in verify_commands(
            step, window.transcript, window.screen_text,
            int(config.get("verify", {}).get("fuzzy_threshold", 90)),
        )] for step, window in zip(steps, windows)]

    checks_data = verify_value if verify_value is not None else _timed("verify", do_verify, timings)
    if verify_value is not None:
        _cache_hit("verify", timings)
    _write_cache(verify_cache, verify_signature, checks_data, cache_enabled)
    checks = [[CheckedCommand(str(item["command"]), str(item["status"])) for item in group] for group in checks_data]

    report("Rendering Markdown")
    render_signature = _signature([steps_data, checks_data])
    render_cache = job_dir / "render.json"
    render_value = _read_cache(render_cache, render_signature, cache_enabled)
    if render_value is None:
        markdown = _timed("render", lambda: render_markdown(list(zip(steps, checks))), timings)
        render_value = {"markdown": markdown}
    else:
        markdown = str(render_value["markdown"])
        _cache_hit("render", timings)
    _write_cache(render_cache, render_signature, render_value, cache_enabled)
    output_path = job_dir / "tutorial.md"
    output_path.write_text(markdown, encoding="utf-8")
    return RunResult(markdown, output_path, timings)


def main() -> None:
    """Run the CLI pipeline and print the generated tutorial location."""
    parser = argparse.ArgumentParser(description="Turn a screen recording into a verified Markdown tutorial.")
    parser.add_argument("video", type=Path, help="Input video path")
    parser.add_argument("--config", type=Path, default=None, help="Optional YAML config path")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = run_pipeline(args.video, args.config)
    print(f"Tutorial written to {result.output_path}")


if __name__ == "__main__":
    main()
