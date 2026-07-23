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
from run_logger import get_logger


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
        return (
            f"Task: {self.task}\n\n"
            f"History so far:\n{history_str}\n\n"
            f"Current URL: {self.session.get_page().url}\n"
            f"Current page interactive elements:\n{elements_str}"
        )

    async def step(self, step_number: int) -> StepRecord:
        """One perceive -> think -> act cycle. Console stays terse (one banner + one result
        line); everything a debugger would actually want — full HTML, raw JS output, the
        exact prompt, the raw LLM response — goes to the structured JSON run log instead."""
        log = get_logger()
        print(f"\n{'=' * 60}\nSTEP {step_number}\n{'=' * 60}")

        # PERCEIVE
        await self.dom.get_interactive_elements()
        elements_str = self.dom.to_string() or "(no interactive elements found)"

        # THINK
        user_message = self._build_user_message(elements_str)
        log.log(
            "agent.py", "Agent.step", "step_start",
            step_number=step_number,
            current_url=self.session.get_page().url,
            history=list(self.history),
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
        )
        messages = [SystemMessage(SYSTEM_PROMPT), UserMessage(user_message)]
        call = chat(messages, ACTIONS, model=self.model)

        # ACT
        try:
            action = parse_action(call, ACTIONS)
            result = await execute(call.name, action, session=self.session, dom=self.dom)
            record = StepRecord(step_number, call.name, call.args, result)
        except Exception as exc:  # deliberately broad: let the LLM see ANY failure and adapt next step
            record = StepRecord(step_number, call.name, call.args, f"{type(exc).__name__}: {exc}", error=True)

        self.history.append(record)
        log.log("agent.py", "Agent.step", "step_end", step_number=step_number, record=record)
        print(record.to_line())
        return record

    async def run(self, max_steps: int = 15) -> str:
        """Loop until `done` is called or max_steps is hit.

        Logs into whatever run is already active (started by the entry point, e.g. a demo
        script, via `run_logger.start_run()` before the browser was even launched) rather
        than starting its own — otherwise the browser-launch events that happen before
        `.run()` is called would be orphaned into a separate untagged log file.
        """
        log = get_logger()
        log.log("agent.py", "Agent.run", "run_start", task=self.task, max_steps=max_steps, model=self.model)
        try:
            for step_number in range(1, max_steps + 1):
                record = await self.step(step_number)
                if record.action == "done" and not record.error:
                    log.finish("done", record.result)
                    return record.result
            result = f"Stopped after {max_steps} steps without calling done."
            log.finish("max_steps_reached", result)
            return result
        except Exception as exc:
            log.log("agent.py", "Agent.run", "run_crashed", error_type=type(exc).__name__, error=str(exc))
            log.finish("crashed", str(exc))
            raise
