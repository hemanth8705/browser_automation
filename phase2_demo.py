"""Phase 2 deliverable: point at a real page, print the indexed interactive-element list,
then prove the index -> element mapping actually works by driving the page through it.

Run: python phase2_demo.py
"""

import asyncio

from browser_session import BrowserProfile, BrowserSession
from dom_service import DomService
from run_logger import start_run


async def main() -> None:
    start_run(task="phase2_demo: extract indexed elements + log in via index resolution")
    async with BrowserSession(BrowserProfile(headless=True)) as session:
        page = session.get_page()
        await page.goto("https://the-internet.herokuapp.com/login")

        dom = DomService(page)
        await dom.get_interactive_elements()

        print("--- Indexed interactive elements ---")
        print(dom.to_string())
        print("-------------------------------------")

        # Prove the index -> element map actually resolves to live elements: fill the
        # username/password fields and submit, purely by index, then check the result.
        elements = dom._elements
        username_idx = next(e.index for e in elements if e.attributes.get("name") == "username")
        password_idx = next(e.index for e in elements if e.attributes.get("name") == "password")
        submit_idx = next(e.index for e in elements if e.tag == "button" and e.attributes.get("type") == "submit")

        await dom.resolve(username_idx).fill("tomsmith")
        await dom.resolve(password_idx).fill("SuperSecretPassword!")
        await dom.resolve(submit_idx).click()

        await page.wait_for_load_state("networkidle")
        flash_text = (await page.locator("#flash").inner_text()).strip()
        print(f"Result after login: {flash_text}")


if __name__ == "__main__":
    asyncio.run(main())
