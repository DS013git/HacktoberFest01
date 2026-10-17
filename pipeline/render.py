"""Render tutorial steps and verification results as Markdown."""

from __future__ import annotations

import re

from pipeline.verify import CheckedCommand
from pipeline.write import Step


def render_markdown(
    steps: list[tuple[Step, list[CheckedCommand]]],
    title: str = "Screen recording tutorial",
) -> str:
    """Build a tutorial with screen-captured code and command evidence."""
    clean_title = " ".join(title.split()) or "Screen recording tutorial"
    lines = [
        f"# {clean_title}",
        "",
        "This guide follows the recorded explanation and includes code captured from the screen.",
        "",
    ]
    total = verified = unverified = 0
    code_count = 0
    for index, (step, checked) in enumerate(steps, start=1):
        lines.extend([f"## Step {index}: {step.title}", "", step.explanation, ""])
        for code_index, block in enumerate(step.code_blocks, start=1):
            code_count += 1
            language = re.sub(r"[^A-Za-z0-9_+#.-]", "", block.language) or "text"
            fence = "```"
            while fence in block.code:
                fence += "`"
            lines.extend([
                f"### Code example {code_index}",
                "",
                f"{fence}{language}",
                block.code,
                fence,
                "",
                "> Extracted from screen text; check unclear characters against the recording.",
                "",
            ])
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
        f"Code blocks captured: {code_count}",
        "",
        "| Total commands | Verified | Unverified |", "|---:|---:|---:|",
        f"| {total} | {verified} | {unverified} |", "",
    ])
    return "\n".join(lines)
