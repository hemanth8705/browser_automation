# Roadmap — Build Your Own "browser-use" (Gemini-first, MVP scope)

## Context

The real [browser-use](https://github.com/browser-use/browser-use) repo (cloned at `../browser-use`) is now a
**~72,000-line production codebase** — `agent/service.py` alone is 4,143 lines, `browser/session.py` is 4,018 lines.
It has grown well past a "browser agent" into a platform: cloud sync, an actor runtime, sandboxing, a skills
marketplace, MCP servers, judge/eval tooling, GIF recording, demo mode, telemetry, and support for 12+ LLM providers.

Cloning that 1:1 is not a realistic or useful learning project. Instead, this roadmap rebuilds the **core
architecture** that actually makes an LLM browser agent work — the same ideas the early versions of browser-use
were built on — using **Gemini only**. Every other provider (OpenAI, Anthropic, etc.) is an explicit *stretch goal
after* the MVP works end to end, per your instruction to "add providers at the end."

**Chosen scope:** Minimal MVP — the essential loop only (browser control → DOM-to-text perception → Gemini
function-calling → action execution → done-condition). No memory, no planner, no GIF recording, no multi-provider
abstraction yet.

**Pace:** Moderate, ~8-12 hrs/week.

**Estimated total effort:** ~45-50 focused hours → **≈ 5-6 calendar weeks** at this pace, done in 7 milestone phases.
Each phase ends in something visibly working — a natural checkpoint to post progress.

---

## How to work each phase (repeat this loop 7 times)

1. **Read** the pointed-to file(s) in `../browser-use/browser_use/...` — skim for *responsibility*, not every line.
   You're extracting the *idea*, not copying code.
2. **Write your own version** from scratch in `browser_automation/`, as small and readable as possible.
3. **Run it, see it work**, before moving on.
4. **Write 3-5 sentences** in your own words in `PROGRESS.md` (create this as you go) — what the piece does, why
   it's designed that way, what surprised you. This is your social-media post draft *and* your own study notes.

---

## Phase 0 — Environment & Orientation (~3 hrs)

**Goal:** Working project skeleton, no automation logic yet.

- Set up `browser_automation/` as its own Python project (uv or venv), Python ≥3.11 to match browser-use.
- Install `playwright` (+ `playwright install chromium`) and `google-genai` (the exact SDK real browser-use uses,
  per `browser-use/pyproject.toml`).
- Confirm your `GOOGLE_API_KEY` in `.env` at the repo root actually works with a 5-line "hello Gemini" script.
- **Read (skim only, orientation):** `browser-use/README.md`, `browser-use/browser_use/__init__.py` — just to see
  what the public API surface looks like, so you know what you're aiming to reproduce a tiny slice of.

**Deliverable:** `python hello_gemini.py` prints a Gemini response. Playwright opens a blank Chromium window and closes it.

**Milestone post idea:** "Day 1 — starting my own browser-use clone from scratch, Gemini-only. Here's the plan: [roadmap]."

---

## Phase 1 — Browser Control Layer (~6 hrs)

**Goal:** A `BrowserSession` class you fully understand, wrapping Playwright.

**Study:**
- `browser-use/browser_use/browser/session.py` (4,018 lines — skim the class docstring + `start`/`navigate`/
  `get_page`/`screenshot`/`close` methods only, ignore the CDP/watchdog internals)
- `browser-use/browser_use/browser/profile.py` (1,288 lines — just the config fields: headless, viewport, user agent)

**Build:**
- `BrowserSession`: `start()` (launch Chromium, new context, new page), `navigate(url)`, `screenshot() -> bytes`,
  `close()`. Async, using Playwright's async API.

**Deliverable:** Script that launches a browser, navigates to `https://example.com`, saves a screenshot, closes cleanly.

**Learning focus:** Playwright's async context manager patterns; why real browser-use separates "profile" (config)
from "session" (runtime state).

---

## Phase 2 — DOM Extraction / "Perception" Layer (~12 hrs — the hardest, most important phase)

**Goal:** Given any live page, produce an **indexed list of interactive elements** — the single trick that makes
LLM-driven browsing possible (an LLM can't click pixels; it can pick "[4] button 'Submit'" from a list).

**Study:**
- `browser-use/browser_use/dom/service.py` (1,174 lines) — focus on how it injects JS into the page to walk the DOM,
  how it decides an element is "interactive" (buttons, links, inputs, `[role=button]`, etc.), and how it assigns
  each one a stable index.
- `browser-use/browser_use/dom/views.py` (1,041 lines) — the data model: what fields does each element node carry
  (tag, text, attributes, bounding box, visibility)?

**Build (simplified):**
- A JS snippet (injected via Playwright's `page.evaluate`) that walks `document.body`, collects interactive
  elements, and returns tag/text/attributes/bounding-box for each.
- A Python function that turns that into a numbered, LLM-readable string, e.g.:
  ```
  [0] <button>Login</button>
  [1] <input type="email" placeholder="Email">
  [2] <a href="/signup">Sign up</a>
  ```
- Keep a Python-side `index -> element handle` map so an action later can say "click index 0" and you resolve it
  back to the real element.

**Deliverable:** Point the script at any real website (e.g. a login page) and get a correct indexed list printed to console.

**Learning focus:** This is where most of the "magic" of these agents actually lives. Expect this phase to take
the longest and be the most rewarding to post about — it's the least obvious part of how these agents work.

---

## Phase 3 — LLM Layer: Gemini Function-Calling (~5 hrs)

**Goal:** A thin wrapper that sends `(system prompt, conversation, available tools)` to Gemini and gets back a
structured "which action, with what arguments" response — no free text parsing.

**Study:**
- `browser-use/browser_use/llm/google/chat.py` (635 lines) — skim how it builds the request, converts message
  history, and interprets Gemini's function-calling response.
- `browser-use/browser_use/llm/messages.py` (238 lines) — the `SystemMessage`/`UserMessage`/`AssistantMessage` types.
- `browser-use/browser_use/llm/schema.py` (217 lines) — how a Pydantic model becomes a JSON schema Gemini understands.

**Build:**
- Simple message dataclasses (or just dicts) for system/user/assistant turns.
- Pydantic models for 3-4 actions (see Phase 4) → converted to Gemini's function-declaration schema.
- A `chat(messages, tools) -> action_call` function using the `google-genai` SDK's function-calling mode.

**Deliverable:** Call it with a fake indexed-element list and a task like "click the login button" → it returns a
structured `{"action": "click", "index": 0}`-shaped object.

**Learning focus:** Structured output / function calling as a way to make LLM output reliably machine-parseable —
the same pattern underlies tool use in Claude, GPT, etc.

---

## Phase 4 — Tools / Actions Layer (~6 hrs)

**Goal:** The concrete actions the agent can take, each one a plain function that touches the browser.

**Study:**
- `browser-use/browser_use/tools/service.py` (2,267 lines — skim only the handful of core actions: click,
  input_text, go_to_url, scroll, done. Ignore file upload, extraction helpers, sandboxing.)
- `browser-use/browser_use/tools/registry/service.py` (601 lines) — the `@registry.action` decorator pattern that
  turns a plain Python function into something the LLM layer can call.

**Build a minimal registry with:**
- `go_to_url(url)`
- `click(index)`
- `input_text(index, text)`
- `scroll(direction)`
- `done(result)` (signals task completion)

**Deliverable:** Manually call each action against a live `BrowserSession` + the Phase 2 index map and watch it work
on a real page (e.g. fill and submit a search box).

**Learning focus:** Why actions are declared once and used for *both* the Gemini schema (Phase 3) *and* execution —
one source of truth instead of two.

---

## Phase 5 — The Agent Loop (~10 hrs — the "it's alive" milestone)

**Goal:** Wire Phases 1-4 into one loop: perceive → think → act → repeat, until `done` or a step limit.

**Study:**
- `browser-use/browser_use/agent/service.py` (4,143 lines — **do not read linearly**; find and read only the main
  `step()` method / run loop to see the shape: get state → build prompt → call LLM → execute action → append to
  history → check done).
- `browser-use/browser_use/agent/message_manager/service.py` (597 lines) — how conversation history is assembled
  and trimmed each step so the context doesn't grow unbounded.
- `browser-use/browser_use/agent/prompts.py` (588 lines) — skim the system prompt structure for inspiration; write
  your own, much shorter version.

**Build:**
- `Agent(task: str, llm, browser)` class with `.run(max_steps=15)`:
  1. Extract indexed elements (Phase 2) from current page.
  2. Build messages: system prompt + task + current state + history.
  3. Call Gemini (Phase 3) → get one action.
  4. Execute it (Phase 4).
  5. Record the step, loop until `done` is called or `max_steps` hit.

**Deliverable:** `agent.run("Search Google for 'browser use' and click the first result")` — and it actually does it,
end to end, no human in the loop.

**Milestone post idea:** "It's alive — my own browser agent clone runs an end-to-end task, Gemini-only, built from scratch." This is your best demo-video moment.

---

## Phase 6 — Polish & Ship the MVP (~5 hrs)

**Goal:** Make it presentable and robust enough to demo.

- Basic error handling: retry once on a failed LLM call or stale element index; fail gracefully past `max_steps`.
- Simple CLI: `python -m browser_automation "your task here"`.
- `README.md` for `browser_automation/`: what it is, architecture diagram (even ASCII), what you learned, explicit
  callout that this is a from-scratch educational rebuild of browser-use's core ideas (not affiliated/endorsed).
- Record a short screen-capture demo (GIF or video) for the social post.

**Deliverable:** A stranger can clone your repo, add their own Gemini key, and run one command to watch it work.

---

## Suggested calendar (8-12 hrs/week)

| Week | Phases | Hours |
|---|---|---|
| 1 | 0 + start of 1 | ~9 |
| 2 | finish 1 + start of 2 | ~10 |
| 3 | finish 2 | ~8 |
| 4 | 3 + 4 | ~11 |
| 5 | 5 | ~10 |
| 6 | 6 (polish + demo) | ~5 |

**Total: ~5-6 weeks to a working, from-scratch, Gemini-only browser agent.**

---

## After the MVP (explicitly out of scope for now, per your "add providers at the end")

Once Phase 6 ships and works, natural next milestones — each is its own small project/post:

1. **Second LLM provider** (e.g. OpenAI) — refactor the Phase 3 wrapper behind a small common interface first.
2. **More actions** — extract page content as markdown, file upload/download, tab management.
3. **Message history trimming/summarization** for long-running tasks.
4. **Retry/self-correction** — let the agent see its own failed action and try a different approach.
5. Only *after* that, look back at real browser-use's `agent/`, `browser/watchdogs/`, `dom/serializer/` for how a
   production system handles the edge cases you'll have hit by then (stale elements, iframes, popups, downloads).

Don't pull these forward — the value of the MVP scope is finishing something real before the codebase grows to
match the original's complexity.
