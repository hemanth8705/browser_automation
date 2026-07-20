"""Phase 3 deliverable: hand Gemini a fake indexed-element list + task, get back a
structured action call — no free text parsing.

Run: python phase3_demo.py
"""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from actions import ACTIONS  # noqa: E402
from gemini_client import chat, parse_action  # noqa: E402
from messages import SystemMessage, UserMessage  # noqa: E402

SYSTEM_PROMPT = """You are a browser automation agent. You are given a task and the current
page's interactive elements as a numbered list. Call exactly one action that makes progress
toward the task. Reference elements by the index shown in brackets, e.g. [0]."""

FAKE_PAGE_STATE = """Current page interactive elements:
[0] <input type="text" name="username"></input>
[1] <input type="password" name="password"></input>
[2] <button type="submit">Login</button>
"""


def main() -> None:
    task = "Click the login button"
    messages = [
        SystemMessage(SYSTEM_PROMPT),
        UserMessage(f"Task: {task}\n\n{FAKE_PAGE_STATE}"),
    ]

    call = chat(messages, ACTIONS)
    print(f"Gemini called: {call.name}({call.args})")

    action = parse_action(call, ACTIONS)
    print(f"Validated action object: {action!r}")


if __name__ == "__main__":
    main()
