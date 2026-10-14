"""Render tutorial steps and verification results as Markdown."""

from __future__ import annotations

from pipeline.verify import CheckedCommand
from pipeline.write import Step


def render_markdown(steps: list[tuple[Step, list[CheckedCommand]]]) -> str:
    """Build numbered Markdown steps and a command verification summary."""
    lines = ["# Screen recording tutorial", ""]
    total = verified = unverified = 0
    for index, (step, checked) in enumerate(steps, start=1):
        lines.extend([f"## Step {index}: {step.title}", "", step.explanation, ""])
        for result in checked:
            total += 1
            if result.status == "unverified":
                unverified += 1
                lines.append(f"⚠️ **UNVERIFIED** — `{result.command}`")
            else:
                verified += 1
                lines.append(f"`{result.command}` — {result.status}")
            lines.extend(["", "```sh", result.command, "```", ""])
    lines.extend([
        "## Verification summary", "",
        "| Total commands | Verified | Unverified |", "|---:|---:|---:|",
        f"| {total} | {verified} | {unverified} |", "",
    ])
    return "\n".join(lines)
