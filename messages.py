"""Phase 3: minimal message types for a chat-style conversation with the LLM.

Real browser-use's messages carry a lot more (multi-part content for images, cache
markers, tool_call ids). We only need plain-text turns for the MVP loop, so content
is just a string.
"""

from dataclasses import dataclass


@dataclass
class SystemMessage:
    content: str


@dataclass
class UserMessage:
    content: str


@dataclass
class AssistantMessage:
    content: str


Message = SystemMessage | UserMessage | AssistantMessage
