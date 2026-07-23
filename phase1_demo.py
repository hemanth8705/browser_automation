"""Phase 1 deliverable: launch a browser, navigate, screenshot, close cleanly.

Run: python phase1_demo.py
"""

import asyncio
from pathlib import Path

from browser_session import BrowserProfile, BrowserSession
from run_logger import start_run


async def main() -> None:
    start_run(task="phase1_demo: launch, navigate, screenshot, close")
    profile = BrowserProfile(headless=True)
    session = BrowserSession(profile)

    await session.start()
    print("Browser started.")

    await session.navigate("https://example.com")
    print(f"Navigated to: {session.get_page().url}")

    screenshot_bytes = await session.screenshot()
    out_path = Path(__file__).parent / "example.png"
    out_path.write_bytes(screenshot_bytes)
    print(f"Saved screenshot ({len(screenshot_bytes)} bytes) to {out_path}")

    await session.close()
    print("Closed cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
