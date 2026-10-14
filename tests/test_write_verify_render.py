"""Tests for writing, verification, and rendering stages."""

from pipeline.align import Window
from pipeline.render import render_markdown
from pipeline.verify import verify_commands
from pipeline.write import Step, write_step


def test_invalid_json_retries_once_then_falls_back() -> None:
    """Two invalid model replies should create an empty-command fallback."""
    calls = []

    def invalid(_prompt: str, _temperature: float) -> str:
        calls.append(1)
        return "not json"

    result = write_step(Window(0, 30, "Create a project", ""), {}, invalid)
    assert len(calls) == 2
    assert result.commands == []
    assert result.explanation == "Create a project"


def test_command_provenance_and_hallucination() -> None:
    """Exact, fuzzy, speech-only, screen-only, and unsupported commands are classified."""
    step = Step("Run", "", ["$ pip install demo", "python app.py", "npm install fake"])
    results = verify_commands(step, "Run pip install demo now", "python app.py", 90)
    assert results[0].status == "verified_speech"
    assert results[1].status == "verified_screen"
    assert results[2].status == "unverified"


def test_exact_fuzzy_and_both_evidence_matches() -> None:
    """Exact containment, RapidFuzz partial matching, and dual-source status work."""
    step = Step("Commands", "", ["git status", "git commit -m save"])
    results = verify_commands(step, "git status", "git statu\ngit commit -m save", 90)
    assert results[0].status == "verified_both"
    assert results[1].status == "verified_screen"


def test_render_marks_unverified_command() -> None:
    """Unverified commands should receive a visible warning and summary count."""
    markdown = render_markdown([(Step("Run", "Run it", ["npm install fake"]),
                                 verify_commands(Step("Run", "", ["npm install fake"]), "", ""))])
    assert "⚠️ **UNVERIFIED**" in markdown
    assert "| 1 | 0 | 1 |" in markdown
