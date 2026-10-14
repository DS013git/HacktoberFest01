"""Tests for media extraction helpers."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline.extract import dedupe_frames


def test_dedupe_drops_identical_consecutive_frames(tmp_path: Path) -> None:
    """Identical adjacent images should be reduced to one kept frame."""
    paths = []
    for index, value in enumerate((20, 20, 220)):
        path = tmp_path / f"{index}.png"
        cv2.imwrite(str(path), np.full((90, 160), value, dtype=np.uint8))
        paths.append((float(index), path))
    kept = dedupe_frames(paths, difference_threshold=8)
    assert [time for time, _ in kept] == [0.0, 2.0]


def test_dedupe_rejects_missing_frame(tmp_path: Path) -> None:
    """Unreadable frames should raise a clear error."""
    with pytest.raises(ValueError, match="Could not read extracted frame"):
        dedupe_frames([(0, tmp_path / "missing.png")])
