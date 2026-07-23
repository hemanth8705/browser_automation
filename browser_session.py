"""Phase 1: a minimal, fully-understood wrapper around Playwright.

Real browser-use splits this into two concepts:
- BrowserProfile: pure config (headless? what viewport? what user agent?) — a "recipe".
- BrowserSession: runtime state built from that recipe (the live browser/context/page).

We keep that same split, just tiny. The reason it matters: config is static and easy to
reason about / pass around, while the session owns things that must be torn down in order
(page -> context -> browser -> playwright) and can only exist once `start()` has run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from run_logger import get_logger


@dataclass
class BrowserProfile:
    """Static launch config. No live objects live here."""

    headless: bool = True
    viewport: dict[str, int] = field(default_factory=lambda: {"width": 1280, "height": 800})
    user_agent: str | None = None


class BrowserSession:
    """Owns one Playwright browser/context/page lifecycle.

    Usage:
        session = BrowserSession(BrowserProfile(headless=False))
        await session.start()
        await session.navigate("https://example.com")
        png_bytes = await session.screenshot()
        await session.close()

    Also works as an async context manager:
        async with BrowserSession(profile) as session:
            await session.navigate(...)
    """

    def __init__(self, profile: BrowserProfile | None = None) -> None:
        self.profile = profile or BrowserProfile()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self) -> None:
        if self._page is not None:
            return  # already started; keep start() idempotent like real browser-use does

        log = get_logger()
        log.log(
            "browser_session.py", "BrowserSession.start", "launching_browser",
            headless=self.profile.headless, viewport=self.profile.viewport, user_agent=self.profile.user_agent,
        )
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.profile.headless)
        self._context = await self._browser.new_context(
            viewport=self.profile.viewport,
            user_agent=self.profile.user_agent,
        )
        self._page = await self._context.new_page()
        log.log("browser_session.py", "BrowserSession.start", "browser_started", page_url=self._page.url)

    def get_page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserSession.start() must be called first")
        return self._page

    async def navigate(self, url: str) -> None:
        log = get_logger()
        log.log("browser_session.py", "BrowserSession.navigate", "navigating", requested_url=url)
        await self.get_page().goto(url)
        log.log("browser_session.py", "BrowserSession.navigate", "navigated", final_url=self.get_page().url)

    async def screenshot(self) -> bytes:
        data = await self.get_page().screenshot()
        get_logger().log("browser_session.py", "BrowserSession.screenshot", "screenshot_taken", size_bytes=len(data))
        return data

    async def close(self) -> None:
        get_logger().log("browser_session.py", "BrowserSession.close", "closing", had_page=self._page is not None)
        # Tear down in the reverse order things were created.
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        self._page = None

    async def __aenter__(self) -> "BrowserSession":
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()
