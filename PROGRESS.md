# Progress Notes

## Phase 0 — Environment & Orientation

Got a Python 3.14 venv running with `playwright` and `google-genai` installed, Chromium
downloaded via `playwright install chromium`, and confirmed the `GOOGLE_API_KEY` in the repo
root `.env` actually talks to Gemini (`hello_gemini.py`) — no silent auth failures waiting to
surprise me later. Skimmed real browser-use's `README.md` and `__init__.py` just to see the
public surface (`Agent`, `BrowserSession`, `Tools`) I'm aiming to reproduce a sliver of. The
main surprise: how little scaffolding Phase 0 actually needs — two ~15-line scripts were
enough to prove the whole toolchain (LLM API + browser automation) works before writing any
real logic.

## Phase 1 — Browser Control Layer

Built `BrowserSession`, a thin wrapper around Playwright's async API with exactly four public
methods: `start()`, `navigate()`, `screenshot()`, `close()`. The interesting design decision,
copied from real browser-use, is splitting **config** (`BrowserProfile` — headless, viewport,
user agent; a plain dataclass with no live objects) from **runtime state** (`BrowserSession` —
the actual Playwright/browser/context/page objects, which only exist between `start()` and
`close()`). Real browser-use does something much heavier under the hood — it talks to Chrome
over raw CDP directly instead of Playwright's own driver, wrapped in an event-bus/watchdog
architecture — but the *shape* is the same idea at 100x the scale. Teardown order matters:
context before browser before playwright itself, mirroring how they were created, which is
also why I added `__aenter__`/`__aexit__` so a bad run can't leak a Chromium process. Verified
end-to-end against `https://example.com`: launched headless, navigated, saved a real
screenshot (`example.png`), closed without hanging processes.
