"""Phase 3/4: the action schema — one Pydantic model per action.

Defining each action once as a Pydantic model is the single source of truth: the same
class produces the JSON schema Gemini sees (Phase 3) and will validate/execute the
arguments Gemini sends back (Phase 4). No separate "tool definition" and "handler
signature" to keep in sync by hand.
"""

from typing import Literal

from pydantic import BaseModel, Field


class GoToUrlAction(BaseModel):
    """Navigate the browser to a URL."""

    url: str = Field(description="The absolute URL to navigate to")


class ClickAction(BaseModel):
    """Click an interactive element identified by its index from the indexed element list."""

    index: int = Field(description="The [index] of the element to click")


class InputTextAction(BaseModel):
    """Type text into an input or textarea element identified by its index."""

    index: int = Field(description="The [index] of the input element")
    text: str = Field(description="The text to type into the element")


class ScrollAction(BaseModel):
    """Scroll the page up or down by roughly one viewport."""

    direction: Literal["up", "down"] = Field(description="Which direction to scroll")


class DoneAction(BaseModel):
    """Signal that the task is complete. Call this once the goal has been achieved."""

    result: str = Field(description="A short summary of what was accomplished")


ACTIONS: dict[str, type[BaseModel]] = {
    "go_to_url": GoToUrlAction,
    "click": ClickAction,
    "input_text": InputTextAction,
    "scroll": ScrollAction,
    "done": DoneAction,
}
