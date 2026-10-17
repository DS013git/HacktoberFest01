"""Generate one structured tutorial step per aligned window."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from rapidfuzz.fuzz import partial_ratio

from pipeline.align import Window


@dataclass(frozen=True)
class CodeBlock:
    """Code shown on screen, with a Markdown language hint."""

    language: str
    code: str


@dataclass(frozen=True)
class Step:
    """A tutorial step with screen code and commands awaiting verification."""

    title: str
    explanation: str
    commands: list[str]
    code_blocks: list[CodeBlock] = field(default_factory=list)


LLMCall = Callable[[str, float], str]


def build_prompt(window: Window) -> str:
    """Create a grounded tutorial-writing prompt for one aligned section."""
    return f"""Write one useful, chronological section of a coding tutorial as strict JSON.
Use this schema: {{"title": string, "explanation": string, "code_blocks": [{{"language": string, "code": string}}], "commands": [string]}}.
Give the section a specific action-oriented title. Explain what the author changes, how it works, and any result or caveat stated in the recording.
Extract useful source code that is visible in the screen text into code_blocks. Keep the code close to the visible text; do not invent missing lines, APIs, values, or behavior, and do not turn spoken descriptions into code. If no code is visible or OCR is too damaged, use an empty code_blocks list.
Use the visible filename/tab to choose a code language when clear; otherwise use "text".
Put shell commands in commands only when the exact command is supported by the transcript or screen text. Do not put CSS, HTML, JavaScript, or other source code in commands. Never invent commands, flags, versions, or package names.
Return valid JSON only, without Markdown fences.

Transcript:
{window.transcript}

Screen text:
{window.screen_text}"""


def _validate_step(raw: str) -> Step:
    """Parse and validate a strict tutorial step JSON response."""
    data = json.loads(raw)
    required = {"title", "explanation", "commands"}
    allowed = required | {"code_blocks"}
    if not isinstance(data, dict) or not required.issubset(data) or not set(data).issubset(allowed):
        raise ValueError("JSON must contain title, explanation, commands, and optional code_blocks")
    if not isinstance(data["title"], str) or not isinstance(data["explanation"], str):
        raise ValueError("title and explanation must be strings")
    if not isinstance(data["commands"], list) or not all(isinstance(item, str) for item in data["commands"]):
        raise ValueError("commands must be a list of strings")
    raw_blocks = data.get("code_blocks", [])
    if not isinstance(raw_blocks, list):
        raise ValueError("code_blocks must be a list")
    code_blocks: list[CodeBlock] = []
    for block in raw_blocks:
        if not isinstance(block, dict) or not isinstance(block.get("language", "text"), str) or not isinstance(block.get("code"), str):
            raise ValueError("each code block must contain string language and code fields")
        code = block["code"].strip("\r\n")
        if code:
            code_blocks.append(CodeBlock(block.get("language", "text").strip() or "text", code))
    return Step(
        data["title"].strip(),
        data["explanation"].strip(),
        [item.strip() for item in data["commands"] if item.strip()],
        code_blocks,
    )


def _code_evidence(code: str, screen_text: str) -> tuple[int, int]:
    """Count meaningful code lines that resemble text captured by screen OCR."""
    source = re.sub(r"[^a-z0-9]+", "", screen_text.casefold())
    lines = [
        re.sub(r"[^a-z0-9]+", "", line.casefold())
        for line in code.splitlines()
    ]
    lines = [line for line in lines if len(line) >= 4]
    if not source or not lines:
        return 0, len(lines)
    supported = sum(1 for line in lines if partial_ratio(line, source) >= 62)
    return supported, len(lines)


def _keep_screen_supported_code(step: Step, screen_text: str) -> Step:
    """Drop code blocks whose meaningful lines do not resemble screen OCR."""
    kept: list[CodeBlock] = []
    for block in step.code_blocks:
        supported, total = _code_evidence(block.code, screen_text)
        required = min(2, total)
        if total and supported >= required and supported / total >= 0.30:
            kept.append(block)
    return Step(step.title, step.explanation, step.commands, kept)


def call_llm(prompt: str, config: dict[str, Any]) -> str:
    """Call the configured OpenAI-compatible chat-completions endpoint."""
    if config.get("offline_mock", False):
        return json.dumps({"title": "Tutorial step", "explanation": "Follow the recorded action.", "commands": []})
    key_name = str(config.get("api_key_env", "SCREEN2TUTORIAL_API_KEY"))
    api_key = os.environ.get(key_name) or str(config.get("api_key", ""))
    if not api_key:
        raise RuntimeError(f"Missing API key: set {key_name} or llm.api_key in config.yaml")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai client is missing; install requirements.txt") from exc
    client = OpenAI(api_key=api_key, base_url=config["base_url"])
    response = client.chat.completions.create(
        model=config["model"],
        temperature=float(config.get("temperature", 0.2)),
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM endpoint returned an empty response")
    return content


def write_step(window: Window, config: dict[str, Any], llm_call: LLMCall | None = None) -> Step:
    """Generate a step, retry invalid JSON once, then fall back safely."""
    prompt = build_prompt(window)
    caller = llm_call or (lambda text, _temperature: call_llm(text, config))
    raw = ""
    for attempt in range(2):
        raw = caller(prompt if attempt == 0 else prompt + "\nYour previous response was invalid. Return valid JSON only.", 0.2)
        try:
            return _keep_screen_supported_code(_validate_step(raw), window.screen_text)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return Step("Recorded step", window.transcript.strip() or "Review the on-screen actions.", [])


def step_to_json(step: Step) -> dict[str, Any]:
    """Convert a step dataclass to a JSON-compatible dictionary."""
    return asdict(step)
