"""Phase 5 deliverable — the "it's alive" milestone: give the agent a task and watch it
run end to end, no human in the loop.

Run: python phase5_demo.py
"""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agent import Agent  # noqa: E402
from browser_session import BrowserProfile, BrowserSession  # noqa: E402

TASK = (
    "Go to youtube and use the search box to search for "
    "'striver a2z play list'. Open the best matching result. Once you've landed on an "
    "play list about it, call done."
)


async def main() -> None:
    async with BrowserSession(BrowserProfile(headless=False)) as session:
        agent = Agent(TASK, session)
        result = await agent.run(max_steps=8)
        print(f"\nFinal result: {result}")
        print(f"Final URL: {session.get_page().url}")


if __name__ == "__main__":
    asyncio.run(main())
