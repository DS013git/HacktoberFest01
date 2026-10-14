"""Tests for speech and OCR alignment."""

from pipeline.align import align_windows
from pipeline.ocr import OCRFrame
from pipeline.transcribe import Segment


def test_align_groups_segments_and_ocr_by_time() -> None:
    """Speech and screen text should land in the correct fixed windows."""
    speech = [Segment(2, 4, "setup"), Segment(62, 64, "run")]
    screen = [OCRFrame(3, "pip install demo\npip install demo"), OCRFrame(63, "python app.py")]
    windows = align_windows(speech, screen, window_seconds=30)
    assert len(windows) == 2
    assert windows[0].transcript == "setup"
    assert windows[0].screen_text == "pip install demo"
    assert windows[1].start == 60
    assert windows[1].transcript == "run"
    assert windows[1].screen_text == "python app.py"
