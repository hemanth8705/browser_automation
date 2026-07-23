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

## Phase 3 — LLM Layer: Gemini Function-Calling

Built the layer that turns "here's a task and the page state" into a structured action
instead of free text: `actions.py` defines each action (`go_to_url`, `click`, `input_text`,
`scroll`, `done`) exactly once as a Pydantic model, and `gemini_client.build_tool()` turns
those straight into Gemini `FunctionDeclaration`s via `model_json_schema()` — no hand-written
schema to keep in sync with the Pydantic fields. `chat()` calls Gemini with
`tool_config=FunctionCallingConfig(mode=ANY)`, which *forces* it to always return a function
call instead of chatting back in plain text — important for an agent loop that always needs
an action, never small talk. The genuinely interesting discovery while studying real
browser-use: it does **not** use native function-calling for Gemini at all — it uses
`response_schema`/JSON mode (ask for JSON matching a schema, then `json.loads()` it), almost
certainly because that pattern is more portable across the 12+ providers it supports, whereas
"native function-calling" looks different per vendor. We used Gemini's native mechanism
instead since going Gemini-only means we can just lean on it directly — a good example of how
"the more general codebase" and "the simpler single-purpose one" can make opposite, both-correct
calls given their different constraints. Tested with a fake indexed element list and four
different task phrasings (click, type text, navigate, and declare done) — Gemini picked the
right action and the right index every time, and Pydantic's `.model_validate()` on the
returned args gave back a real typed object, not a dict to keep guessing about.

## Phase 4 — Tools / Actions Layer

`registry.py` is the layer where the Pydantic action models from Phase 3 finally touch a
real browser: `@action("click")` registers a handler under the exact same name as the
`ACTIONS` dict, and an `assert set(REGISTRY) == set(ACTIONS)` at import time makes it
impossible to add an action to one side and forget the other — drift becomes an immediate
import-time crash instead of a confusing runtime `KeyError` three steps into an agent run.
Each handler declares only the context it actually needs (`params`, plus `session` and/or
`dom`) as named parameters, and `execute()` inspects the handler's signature and only passes
along what it asked for — a tiny version of the dependency-injection trick real browser-use's
registry does at much larger scale (it injects `browser_session`, `file_system`,
`page_extraction_llm`, and more, matched by parameter name). Ran all five actions manually
against a live Wikipedia page: `go_to_url` → `input_text` into the search box (found by index)
→ `scroll` → `click` the search button (also by index) → landed on the real
`Browser_automation` article → `done`. One real surprise along the way: my first target for
this demo was DuckDuckGo's HTML search, and it actually blocked the headless browser with a
"select all squares containing a duck" bot-challenge — a good reminder that real websites
actively fight automation, and production browser-use has to deal with exactly this kind of
thing (the `handle_browser_error` / retry logic I skimmed in Phase 4's source makes a lot
more sense now that I've hit a live example of why it exists).

## Phase 5 — The Agent Loop ("it's alive")

`agent.py` is where Phases 1-4 stop being separate parts and become one thing: `step()` does
perceive (fresh `DomService` extraction) → think (`chat()` with a rebuilt state message) → act
(`execute()`) → record, and `run()` just calls `step()` in a loop until `done` or `max_steps`.
The single biggest design decision, copied from real browser-use's message manager, is that the
conversation sent to Gemini is **always exactly two messages** — the system prompt plus one
`UserMessage` that gets completely rebuilt every step (task + a one-line-per-step history +
current URL + current element list) — never an ever-growing transcript of every past message.
Old DOM snapshots are simply never resent; only today's. This is *the* answer to "won't context
explode over a long run" and it's a much simpler trick than it sounds like from the outside.

The genuinely exciting result: gave it the task "search Wikipedia for 'browser automation' and
open the best match," with zero pre-scripted steps, and the FIRST run wasn't even a clean
success story — it was better than one. Step 1 called `go_to_url(url='en.wikipedia.org')`
(missing the `https://` scheme) and Playwright rejected it; that error text flowed into step 2's
history, and the model retried with `https://en.wikipedia.org` on its own — nobody coded a
URL-fixup rule, it just saw its own mistake and adapted, because the system prompt says "if the
last action errored, don't repeat it, try something different." A few steps later a `click`
timed out (the search suggestions dropdown likely covered the target), and it recovered again,
clicked a different index, and correctly called `done` once it had actually landed on the
article. A second run completed the same task in 5 clean steps with zero errors. This is the
whole roadmap's thesis in one demo: an agent isn't "an LLM that never makes mistakes," it's a
loop where mistakes become visible feedback instead of crashes — the self-correction isn't a
separate feature, it falls straight out of "feed the error back in and ask again."

## Infrastructure — Structured Per-Run JSON Logging

Not a roadmap phase, but needed the moment the agent stopped doing obviously-correct things:
once step 4 timed out on a click, the natural next question was "what did the DOM actually look
like right then, and what exactly did Gemini see?" — and scrollback console prints don't answer
that once a run is more than a few steps long. `run_logger.py` gives every run one file,
`logs/log_<date>_<time>.json`, and every meaningful function across every file (`BrowserSession`,
`DomService`, `gemini_client`, `registry`, `Agent`) writes one entry into it tagged with exactly
the file/function/event that produced it, plus whatever variables mattered — the full page HTML
`DomService` read, the raw JS-extractor output before it became `InteractiveElement`s, the exact
system+user messages sent to Gemini, the raw function-call response, the validated action, and
the execution result or error. The file is rewritten after every single entry, not just at the
end, so a hard crash still leaves the full trail up to the failure — directly answering "which
step, which variable, first went wrong."

Two real bugs turned up while building this, both more interesting than the logging code itself:

1. **"Readable" isn't the same as "has newlines."** My first cut split long strings on `\n` so
   they'd render as a JSON array instead of an escaped `\n`-soup blob. That works for the LLM
   prompts, but real page HTML comes back from the browser **minified onto one giant line with
   no `\n` at all** — Wikipedia's full HTML is 363,000 characters as effectively one "line." The
   fix was real fixed-width word-wrapping (`textwrap.wrap` at 200 chars), not just splitting on
   whatever whitespace happens to already be there. Lesson: when you're formatting for human
   eyes, check your assumption against the ugliest real input, not the prompt text you tested
   with first.

2. **Fragmented logs from an implicit "start."** My first version had `Agent.run()` call
   `start_run()`, which seemed natural — "a run starts when you call run()." But
   `BrowserSession.start()` fires earlier, inside the demo script's `async with BrowserSession(...)`
   block, and it also calls the logger — which auto-starts its own untagged run since nothing had
   called `start_run()` yet. Result: two log files per invocation, with the browser-launch events
   orphaned in one and everything else in another. The fix was to move `start_run()` to the
   actual entry point (the top of each `phaseN_demo.py`'s `main()`, before the browser is even
   constructed) and have `Agent.run()` just use whatever run is already active. The general
   lesson: **"when does this unit of work start" is a question about the outermost caller, not
   whichever function happens to have a convenient-sounding name** — a library-ish class
   (`Agent`) shouldn't assume it owns the boundary of an operation that other code (the
   `BrowserSession` construction) already started before it was ever called.
