"""Check every generated command against transcript and OCR evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz.fuzz import partial_ratio

from pipeline.write import Step


@dataclass(frozen=True)
class CheckedCommand:
    """A command and its evidence-based verification status."""

    command: str
    status: str


def normalize_text(text: str) -> str:
    """Normalize whitespace, quotation marks, and common shell prompts."""
    cleaned = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    cleaned = re.sub(r"(?m)^\s*(?:\$|>)\s+", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().casefold()


def _matches(command: str, source: str, threshold: int) -> bool:
    """Match short commands as whole words; otherwise allow exact or fuzzy matches."""
    needle = normalize_text(command)
    haystack = normalize_text(source)
    if not needle or not haystack:
        return False
    if len(needle) <= 3:
        return re.search(rf"\b{re.escape(needle)}\b", haystack) is not None
    return needle in haystack or partial_ratio(needle, haystack) >= threshold


def verify_commands(
    step: Step, transcript: str, screen_text: str, threshold: int = 90
) -> list[CheckedCommand]:
    """Assign a status to each command based on speech and screen evidence."""
    checked: list[CheckedCommand] = []
    for command in step.commands:
        in_speech = _matches(command, transcript, threshold)
        in_screen = _matches(command, screen_text, threshold)
        if in_speech and in_screen:
            status = "verified_both"
        elif in_screen:
            status = "verified_screen"
        elif in_speech:
            status = "verified_speech"
        else:
            status = "unverified"
        checked.append(CheckedCommand(command, status))
    return checked
