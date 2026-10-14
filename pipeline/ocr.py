"""Read on-screen text from sampled video frames with Tesseract."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OCRFrame:
    """Recognized screen text and its video timestamp."""

    timestamp: float
    text: str


def clean_ocr_text(text: str) -> str:
    """Remove blank lines and lines made mostly of OCR noise."""
    clean_lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        useful = sum(char.isalnum() for char in line)
        if line and useful >= 2 and useful / max(len(line), 1) >= 0.25:
            clean_lines.append(line)
    return "\n".join(clean_lines)


def ocr_frames(
    frames: list[tuple[float, Path]], tesseract_cmd: str = "", engine: Any | None = None
) -> list[OCRFrame]:
    """Run Tesseract against frames and return non-empty timestamped text."""
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("pytesseract is missing; install requirements.txt") from exc
    if engine is None:
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        engine = pytesseract
    output: list[OCRFrame] = []
    for timestamp, path in frames:
        if not Path(path).is_file():
            raise ValueError(f"Frame does not exist: {path}")
        try:
            text = clean_ocr_text(engine.image_to_string(str(path)))
        except Exception as exc:
            raise RuntimeError(
                f"Tesseract could not process {path}; install Tesseract or set ocr.tesseract_cmd in config.yaml: {exc}"
            ) from exc
        if text:
            output.append(OCRFrame(float(timestamp), text))
    return output


def ocr_to_json(frames: list[OCRFrame]) -> list[dict[str, Any]]:
    """Convert OCR dataclasses to JSON-compatible dictionaries."""
    return [asdict(frame) for frame in frames]
