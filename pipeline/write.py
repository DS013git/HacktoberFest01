"""Generate one structured tutorial step per aligned window."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable

from pipeline.align import Window


@dataclass(frozen=True)
class Step:
    """A tutorial step with commands awaiting verification."""

    title: str
    explanation: str
    commands: list[str]


LLMCall = Callable[[str, float], str]


def build_prompt(window: Window) -> str:
    """Create the constrained prompt for a tutorial step."""
    return f"""Write exactly one concise step for a developer tutorial as strict JSON with keys title, explanation, commands.
Use this schema: {{"title": string, "explanation": string, "commands": [string]}}.
Only include a command if that command appears in the transcript or screen text below.
Never invent flags, versions, package names, or commands. If no command is evidenced, use an empty commands list.
Do not wrap the JSON in Markdown fences.

Transcript:
{window.transcript}

Screen text:
{window.screen_text}"""


def _validate_step(raw: str) -> Step:
    """Parse and validate a strict tutorial step JSON response."""
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"title", "explanation", "commands"}:
        raise ValueError("JSON must contain exactly title, explanation, and commands")
    if not isinstance(data["title"], str) or not isinstance(data["explanation"], str):
        raise ValueError("title and explanation must be strings")
    if not isinstance(data["commands"], list) or not all(isinstance(item, str) for item in data["commands"]):
        raise ValueError("commands must be a list of strings")
    return Step(data["title"].strip(), data["explanation"].strip(), [item.strip() for item in data["commands"] if item.strip()])


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
            return _validate_step(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return Step("Recorded step", window.transcript.strip() or "Review the on-screen actions.", [])


def step_to_json(step: Step) -> dict[str, Any]:
    """Convert a step dataclass to a JSON-compatible dictionary."""
    return asdict(step)
