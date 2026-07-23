"""Phase 4 deliverable: manually call each action against a live BrowserSession + the
Phase 2 index map, and watch it fill and submit a real search box.

Run: python phase4_demo.py
"""

import asyncio

from actions import ClickAction, DoneAction, GoToUrlAction, InputTextAction, ScrollAction
from browser_session import BrowserProfile, BrowserSession
from dom_service import DomService
from registry import execute
from run_logger import start_run


async def main() -> None:
    start_run(task="phase4_demo: manually drive go_to_url/input_text/scroll/click/done")
    async with BrowserSession(BrowserProfile(headless=True)) as session:
        dom = DomService(session.get_page())

        print(await execute("go_to_url", GoToUrlAction(url="https://en.wikipedia.org/wiki/Main_Page"), session=session, dom=dom))

        await dom.get_interactive_elements()
        print(dom.to_string())

        query_index = next(e.index for e in dom._elements if e.attributes.get("name") == "search")
        submit_index = next(e.index for e in dom._elements if e.tag == "button" and e.text == "Search")

        print(await execute("input_text", InputTextAction(index=query_index, text="browser automation"), session=session, dom=dom))
        print(await execute("scroll", ScrollAction(direction="down"), session=session, dom=dom))
        print(await execute("click", ClickAction(index=submit_index), session=session, dom=dom))

        await session.get_page().wait_for_load_state("domcontentloaded")
        print(f"Landed on: {session.get_page().url}")

        await dom.get_interactive_elements()
        result_links = [e for e in dom._elements if e.tag == "a" and e.text]
        print(f"\nResults page loaded — {len(result_links)} links found, first few:")
        for e in result_links[:5]:
            print(f"  {e.to_line()}")

        print(await execute("done", DoneAction(result=f"Searched for 'browser automation', found {len(result_links)} links"), session=session, dom=dom))


if __name__ == "__main__":
    asyncio.run(main())
