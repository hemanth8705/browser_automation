"""Phase 0 sanity check: confirm Playwright can launch and close a browser.

Run: python hello_browser.py
"""

import asyncio

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        print("Blank Chromium window opened.")
        await page.wait_for_timeout(1000)
        await browser.close()
        print("Closed cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
