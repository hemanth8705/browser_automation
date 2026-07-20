"""Phase 2: DOM extraction / "perception" layer.

The core trick that makes LLM-driven browsing possible: an LLM can't click pixels, it can
only pick from text. So we turn a live page into a numbered list of interactive elements,
e.g. "[0] <button>Login</button>", hand that to the LLM, and let it say "click index 0".

The other half of the trick is getting back FROM an index TO a real element. We do that by
having the injected JS stamp a `data-baidx="N"` attribute onto each element it indexes, so
`resolve(n)` is just a Playwright locator for `[data-baidx="n"]` — no separate handle table
to keep in sync with a changing page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Locator, Page

_EXTRACTOR_JS = (Path(__file__).parent / "dom_extractor.js").read_text(encoding="utf-8")


@dataclass
class InteractiveElement:
    index: int
    tag: str
    text: str
    attributes: dict[str, str] = field(default_factory=dict)

    def to_line(self) -> str:
        attrs = " ".join(f'{k}="{v}"' for k, v in self.attributes.items())
        opening = f"<{self.tag}{' ' + attrs if attrs else ''}>"
        return f"[{self.index}] {opening}{self.text}</{self.tag}>"


class DomService:
    """Extracts an indexed, LLM-readable list of interactive elements from a page."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self._elements: list[InteractiveElement] = []

    async def get_interactive_elements(self) -> list[InteractiveElement]:
        raw = await self.page.evaluate(_EXTRACTOR_JS)
        self._elements = [
            InteractiveElement(index=item["index"], tag=item["tag"], text=item["text"], attributes=item["attributes"])
            for item in raw
        ]
        return self._elements

    def to_string(self) -> str:
        return "\n".join(el.to_line() for el in self._elements)

    def resolve(self, index: int) -> Locator:
        """Map an index from the last extraction back to the live element."""
        return self.page.locator(f'[data-baidx="{index}"]')
