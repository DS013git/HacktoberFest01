"""Extract audio and interval-spaced video frames, then remove redundant frames."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np


def extract_media(
    video_path: Path,
    output_dir: Path,
    frame_interval_seconds: int = 2,
    ffmpeg_path: str = "ffmpeg",
) -> tuple[Path, list[tuple[float, Path]]]:
    """Create a 16 kHz mono WAV and PNG frames sampled at a fixed interval."""
    source = Path(video_path)
    if not source.is_file():
        raise ValueError(f"Unreadable video: file does not exist: {source}")
    executable = shutil.which(ffmpeg_path) if not Path(ffmpeg_path).is_file() else ffmpeg_path
    if not executable:
        raise RuntimeError("ffmpeg was not found; install it or set extract.ffmpeg_path in config.yaml")
    if frame_interval_seconds < 1:
        raise ValueError("frame_interval_seconds must be at least 1")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    frames_dir = output / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output / "audio.wav"
    frame_pattern = frames_dir / "frame-%06d.png"
    commands = [
        [executable, "-y", "-v", "error", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)],
        [executable, "-y", "-v", "error", "-i", str(source), "-vf", f"fps=1/{frame_interval_seconds}", "-vsync", "vfr", str(frame_pattern)],
    ]
    try:
        for command in commands:
            subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or str(exc)
        raise ValueError(f"Could not read video with ffmpeg: {detail}") from exc

    paths = sorted(frames_dir.glob("frame-*.png"))
    if not audio_path.is_file() or not paths:
        raise ValueError(f"Unreadable video: ffmpeg produced no audio or frames for {source}")
    frames = [(index * frame_interval_seconds, path) for index, path in enumerate(paths)]
    return audio_path, frames


def dedupe_frames(
    frames: list[tuple[float, Path]], difference_threshold: float = 8.0
) -> list[tuple[float, Path]]:
    """Keep frames with sufficient grayscale mean difference from the last kept frame."""
    if difference_threshold < 0:
        raise ValueError("difference_threshold must be non-negative")
    kept: list[tuple[float, Path]] = []
    previous: np.ndarray | None = None
    for timestamp, path in frames:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"Could not read extracted frame: {path}")
        small = cv2.resize(image, (160, 90), interpolation=cv2.INTER_AREA)
        if previous is None or float(np.mean(cv2.absdiff(previous, small))) > difference_threshold:
            kept.append((timestamp, path))
            previous = small
    return kept
