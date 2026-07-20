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

## Phase 2 — DOM Extraction / "Perception" Layer

This is the actual trick that makes LLM browsing possible: an LLM can't click pixels, so
`dom_extractor.js` walks `document.body` and turns every interactive element into a line like
`[2] <input type="text" name="username"></input>`, which is just... text a model can read and
reference. Interactivity is a heuristic stack (tag whitelist, ARIA role, `onclick`/`tabindex`,
`contenteditable`, and a `cursor:pointer` fallback) plus a visibility check (non-zero size, not
`display:none`/`hidden`/transparent, actually inside the current viewport) — real browser-use
does the same idea but backed by the CDP accessibility tree and paint-order data instead of
raw `getComputedStyle` calls, since that's more robust at production scale. The index-to-element
mapping doesn't need a separate lookup table: the JS stamps `data-baidx="N"` directly onto the
DOM element, so `DomService.resolve(n)` is just a Playwright locator for `[data-baidx="n"]` —
simpler than real browser-use's CDP `backendNodeId` approach, but the same core idea (the index
*is* a handle back to the real node). Proved it end-to-end on a real login page
(the-internet.herokuapp.com/login): extracted the list, filled username/password and clicked
submit purely by index, and got "You logged into a secure area!" back — the mapping actually
works, not just the printout. Genuinely interesting surprise: the "Fork me on GitHub" ribbon's
`<a>` wrapper had a collapsed zero-size box (its `<img>` child was absolutely positioned out of
flow), so my visibility check correctly skipped the zero-size anchor and fell through to index
the `<img>` itself instead — an emergent, *correct* behavior I didn't special-case for, and a
small taste of why real browser-use's visibility/paint-order logic is so much more elaborate
than mine: DOM layout has endless little quirks like this.
