"""Run CPU English speech recognition with faster-whisper."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Segment:
    """A timestamped transcript segment."""

    start: float
    end: float
    text: str


def transcribe_audio(
    audio_path: Path,
    model_name: str = "base",
    compute_type: str = "int8",
    device: str = "cpu",
    language: str = "en",
    model: Any | None = None,
) -> list[Segment]:
    """Transcribe a WAV file with faster-whisper on CPU."""
    source = Path(audio_path)
    if not source.is_file():
        raise ValueError(f"Audio file does not exist: {source}")
    if model is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError("faster-whisper is missing; install requirements.txt") from exc
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _ = model.transcribe(str(source), language=language)
    return [Segment(float(item.start), float(item.end), str(item.text).strip()) for item in segments]


def segments_to_json(segments: list[Segment]) -> list[dict[str, Any]]:
    """Convert transcript dataclasses to JSON-compatible dictionaries."""
    return [asdict(segment) for segment in segments]
