"""End-to-end structured logging for one agent run.

Every meaningful step of the pipeline — the exact HTML we read, the raw JS-extractor
output, the exact messages sent to Gemini, the raw response, the action executed —
gets appended as one entry to a single JSON file per run: `logs/log_<date>_<time>.json`.

Each entry is tagged with the file/function/event that produced it, plus a `variables`
dict of whatever that call site wanted visible. If a run does the wrong thing, you open
one file and can see exactly which step, and which variable, first went sideways.

Design notes:
- The file is rewritten after every single log call (not just at the end), so a crash
  never loses the trail — you always have everything logged up to the failure.
- Multi-line strings (HTML, prompts, formatted element lists) are stored as a LIST of
  lines, not one \\n-escaped blob — that's what makes the saved JSON actually readable
  by eye instead of a wall of "\\n" escape codes.
- A generous but finite string cap keeps one huge page's HTML from ballooning the file
  across many steps.
"""

from __future__ import annotations

import dataclasses
import json
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

LOGS_DIR = Path(__file__).parent / "logs"
_MAX_STR_LEN = 50_000  # generous; only truly huge values (full page HTML) ever hit this
_WRAP_WIDTH = 200  # real-world HTML/JS is often minified onto one giant line with no \n
# at all, so splitting on "\n" alone wouldn't make it readable — we hard-wrap too.


def _wrap_text(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line:
            lines.append("")
        elif len(raw_line) <= _WRAP_WIDTH:
            lines.append(raw_line)
        else:
            lines.extend(textwrap.wrap(raw_line, width=_WRAP_WIDTH, break_long_words=True, break_on_hyphens=False))
    return lines


def _to_json_safe(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) > _MAX_STR_LEN:
            value = value[:_MAX_STR_LEN] + f"...[truncated, {len(value)} total chars]"
        if len(value) <= _WRAP_WIDTH and "\n" not in value:
            return value  # short one-liners stay plain strings, no need to wrap
        return _wrap_text(value)
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(v) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _to_json_safe(dataclasses.asdict(value))
    if hasattr(value, "model_dump"):  # pydantic BaseModel
        return _to_json_safe(value.model_dump())
    if isinstance(value, Path):
        return str(value)
    return value


class RunLogger:
    """One instance per run; writes to `logs/log_<timestamp>.json`."""

    def __init__(self, task: str | None = None) -> None:
        LOGS_DIR.mkdir(exist_ok=True)
        self.run_id = datetime.now().strftime("log_%Y%m%d_%H%M%S")
        self.path = LOGS_DIR / f"{self.run_id}.json"
        self._meta: dict[str, Any] = {
            "run_id": self.run_id,
            "task": task,
            "started_at": datetime.now().isoformat(timespec="milliseconds"),
            "ended_at": None,
            "status": "running",
            "final_result": None,
        }
        self._entries: list[dict[str, Any]] = []
        self._seq = 0
        self._flush()

    def log(self, file: str, function: str, event: str, **variables: Any) -> None:
        """Record one entry: which file/function/event produced which variables."""
        self._seq += 1
        self._entries.append(
            {
                "seq": self._seq,
                "timestamp": datetime.now().isoformat(timespec="milliseconds"),
                "file": file,
                "function": function,
                "event": event,
                "variables": {name: _to_json_safe(val) for name, val in variables.items()},
            }
        )
        self._flush()

    def finish(self, status: str, result: str | None = None) -> None:
        self._meta["ended_at"] = datetime.now().isoformat(timespec="milliseconds")
        self._meta["status"] = status
        self._meta["final_result"] = result
        self._flush()

    def _flush(self) -> None:
        payload = {**self._meta, "entries": self._entries}
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


_active: RunLogger | None = None


def start_run(task: str | None = None) -> RunLogger:
    """Start a fresh log file for a new run. Call this once per task/agent run."""
    global _active
    _active = RunLogger(task)
    return _active


def get_logger() -> RunLogger:
    """The active run's logger, auto-starting an untagged run if nothing started one yet."""
    global _active
    if _active is None:
        _active = RunLogger(task=None)
    return _active
