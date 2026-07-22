"""Phase 5: the agent loop — perceive -> think -> act -> repeat.

This is the piece that turns Phases 1-4 from "a pile of parts that work in isolation" into
something that runs a task end to end with no human in the loop.

Context-growth note (the thing message_manager/service.py in real browser-use spends 600
lines on): we do NOT append a new message to the conversation every step. Each call to
Gemini is exactly two messages — the system prompt and ONE freshly-rebuilt user message
containing the task, a compact one-line-per-step history, and the current page state. The
message list stays constant size forever; only that one message's *content* changes. Old
DOM snapshots are never resent — only today's.
"""

from __future__ import annotations

from dataclasses import dataclass

from actions import ACTIONS
from browser_session import BrowserSession
from dom_service import DomService
from gemini_client import chat, parse_action
from messages import SystemMessage, UserMessage
from prompts import SYSTEM_PROMPT
from registry import execute


@dataclass
class StepRecord:
    step: int
    action: str
    args: dict
    result: str
    error: bool = False

    def to_line(self) -> str:
        status = "ERROR" if self.error else "OK"
        return f"Step {self.step}: {self.action}({self.args}) -> [{status}] {self.result}"


class Agent:
    """Wires BrowserSession + DomService + Gemini + the action registry into a loop."""

    def __init__(self, task: str, session: BrowserSession, model: str = "gemini-2.5-flash") -> None:
        self.task = task
        self.session = session
        self.model = model
        self.dom = DomService(session.get_page())
        self.history: list[StepRecord] = []

    def _build_user_message(self, elements_str: str) -> str:
        history_str = "\n".join(r.to_line() for r in self.history) or "(no actions taken yet)"

        print("\nBuilding user message...")
        print("Task:")
        print(self.task)

        print("\nHistory String:")
        print(history_str)

        print("\nCurrent URL:")
        print(self.session.get_page().url)

        print("\nElements String:")
        print(elements_str)

        message = (
            f"Task: {self.task}\n\n"
            f"History so far:\n{history_str}\n\n"
            f"Current URL: {self.session.get_page().url}\n"
            f"Current page interactive elements:\n{elements_str}"
        )

        return message


    async def step(self, step_number: int) -> StepRecord:
        """One perceive -> think -> act cycle."""

        print("\n" + "=" * 100)
        print(f"STEP {step_number}")
        print("=" * 100)

        # -----------------------------
        # PERCEPTION
        # -----------------------------
        await self.dom.get_interactive_elements()
        elements_str = self.dom.to_string() or "(no interactive elements found)"

        print("\n[Current URL]")
        print(self.session.get_page().url)

        print("\n[Interactive Elements]")
        print(elements_str)

        # -----------------------------
        # BUILD USER MESSAGE
        # -----------------------------
        user_message = self._build_user_message(elements_str)

        print("\n[History]")
        if self.history:
            for record in self.history:
                print(record.to_line())
        else:
            print("(no actions taken yet)")

        print("\n[System Prompt]")
        print(SYSTEM_PROMPT)

        print("\n[User Prompt Sent To LLM]")
        print(user_message)

        # -----------------------------
        # BUILD MESSAGE LIST
        # -----------------------------
        messages = [
            SystemMessage(SYSTEM_PROMPT),
            UserMessage(user_message),
        ]

        print("\n[Messages Passed To chat()]")
        for i, msg in enumerate(messages):
            print("-" * 80)
            print(f"Message {i}")
            print(f"Type: {type(msg).__name__}")
            print(msg)

        # -----------------------------
        # TOOLS
        # -----------------------------
        print("\n[Registered Tools]")
        for tool in ACTIONS:
            print(tool)

        print("\nCalling Gemini...")
        call = chat(messages, ACTIONS, model=self.model)

        print("\n[Raw LLM Response]")
        print(call)

        try:
            print("\nParsing action...")
            action = parse_action(call, ACTIONS)

            print("\n[Parsed Action]")
            print(action)

            print("\nTool Name:")
            print(call.name)

            print("\nTool Arguments:")
            print(call.args)

            print("\nExecuting Tool...")
            result = await execute(
                call.name,
                action,
                session=self.session,
                dom=self.dom,
            )

            print("\n[Tool Result]")
            print(result)

            record = StepRecord(
                step_number,
                call.name,
                call.args,
                result,
            )

        except Exception as exc:
            print("\n[ERROR]")
            print(type(exc).__name__)
            print(exc)

            record = StepRecord(
                step_number,
                call.name,
                call.args,
                f"{type(exc).__name__}: {exc}",
                error=True,
            )

        self.history.append(record)

        print("\n[Updated History]")
        for r in self.history:
            print(r.to_line())

        print("=" * 100)
        print("END STEP")
        print("=" * 100 + "\n")

        return record
    
    
    async def run(self, max_steps: int = 15) -> str:
        """Loop until `done` is called or max_steps is hit."""
        for step_number in range(1, max_steps + 1):
            record = await self.step(step_number)
            print(record.to_line())
            if record.action == "done" and not record.error:
                return record.result
        return f"Stopped after {max_steps} steps without calling done."
