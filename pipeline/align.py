"""Group speech and screen text into time-bounded tutorial windows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from pipeline.ocr import OCRFrame
from pipeline.transcribe import Segment


@dataclass(frozen=True)
class Window:
    """Transcript and OCR evidence associated with one time window."""

    start: float
    end: float
    transcript: str
    screen_text: str


def align_windows(
    segments: list[Segment], ocr_frames: list[OCRFrame], window_seconds: int = 45
) -> list[Window]:
    """Group transcript and OCR records into windows starting at fixed intervals."""
    if window_seconds < 1:
        raise ValueError("window_seconds must be at least 1")
    if not segments and not ocr_frames:
        return []
    start_time = min([item.start for item in segments] + [item.timestamp for item in ocr_frames])
    end_time = max([item.end for item in segments] + [item.timestamp for item in ocr_frames])
    first_bucket = int(start_time // window_seconds)
    last_bucket = int(end_time // window_seconds)
    result: list[Window] = []
    for bucket in range(first_bucket, last_bucket + 1):
        start = float(bucket * window_seconds)
        end = float((bucket + 1) * window_seconds)
        speech = [item.text.strip() for item in segments if item.start < end and item.end > start and item.text.strip()]
        screen_lines: list[str] = []
        seen: set[str] = set()
        for frame in ocr_frames:
            if start <= frame.timestamp < end:
                for line in frame.text.splitlines():
                    clean = line.strip()
                    key = clean.casefold()
                    if clean and key not in seen:
                        seen.add(key)
                        screen_lines.append(clean)
        if speech or screen_lines:
            result.append(Window(start, end, " ".join(speech), "\n".join(screen_lines)))
    return result


def windows_to_json(windows: Iterable[Window]) -> list[dict[str, object]]:
    """Convert window dataclasses to JSON-compatible dictionaries."""
    return [asdict(window) for window in windows]
