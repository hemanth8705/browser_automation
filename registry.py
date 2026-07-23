"""Phase 4: Tools / Actions layer — plain functions that actually touch the browser.

Each handler is registered under the same name used in actions.py's Pydantic models
(Phase 3), so the schema Gemini sees and the code that actually runs can never define
two different things called "click". Handlers ask for whatever context they need
(session, dom) just by parameter name; `execute()` only passes what a given handler
declared — a small version of the dependency-injection trick real browser-use's
registry does with `inspect.signature` over a much larger "special params" table.
"""

from __future__ import annotations

import inspect
from typing import Awaitable, Callable

from pydantic import BaseModel

from actions import ACTIONS, ClickAction, DoneAction, GoToUrlAction, InputTextAction, ScrollAction
from browser_session import BrowserSession
from dom_service import DomService
from run_logger import get_logger

REGISTRY: dict[str, Callable[..., Awaitable[str]]] = {}


def action(name: str):
    def decorator(fn: Callable[..., Awaitable[str]]) -> Callable[..., Awaitable[str]]:
        REGISTRY[name] = fn
        return fn

    return decorator


@action("go_to_url")
async def _go_to_url(params: GoToUrlAction, session: BrowserSession) -> str:
    await session.navigate(params.url)
    result = f"Navigated to {params.url}"
    get_logger().log("registry.py", "_go_to_url", "action_executed", params=params, result=result)
    return result


@action("click")
async def _click(params: ClickAction, dom: DomService) -> str:
    await dom.resolve(params.index).click()
    result = f"Clicked index {params.index}"
    get_logger().log("registry.py", "_click", "action_executed", params=params, result=result)
    return result


@action("input_text")
async def _input_text(params: InputTextAction, dom: DomService) -> str:
    await dom.resolve(params.index).fill(params.text)
    result = f"Typed {params.text!r} into index {params.index}"
    get_logger().log("registry.py", "_input_text", "action_executed", params=params, result=result)
    return result


@action("scroll")
async def _scroll(params: ScrollAction, session: BrowserSession) -> str:
    delta = 600 if params.direction == "down" else -600
    await session.get_page().mouse.wheel(0, delta)
    result = f"Scrolled {params.direction}"
    get_logger().log("registry.py", "_scroll", "action_executed", params=params, result=result)
    return result


@action("done")
async def _done(params: DoneAction) -> str:
    get_logger().log("registry.py", "_done", "action_executed", params=params, result=params.result)
    return params.result


# One name, one meaning: every action declared in actions.py must have a handler here
# and vice versa. This catches drift (add an action, forget the handler, or typo a name)
# at import time instead of as a mysterious runtime KeyError mid-agent-run.
assert set(REGISTRY) == set(ACTIONS), (set(REGISTRY), set(ACTIONS))


async def execute(name: str, params: BaseModel, *, session: BrowserSession, dom: DomService) -> str:
    """Look up the handler for `name` and call it with only the context it asked for."""
    log = get_logger()
    handler = REGISTRY[name]
    available = {"params": params, "session": session, "dom": dom}
    kwargs = {p: available[p] for p in inspect.signature(handler).parameters if p in available}
    log.log(
        "registry.py", "execute", "dispatching",
        action_name=name, params=params, handler_name=handler.__name__, injected_context=list(kwargs),
    )
    result = await handler(**kwargs)
    log.log("registry.py", "execute", "dispatched", action_name=name, result=result)
    return result
