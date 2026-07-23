"""Phase 3: LLM layer — Gemini function-calling, no free-text parsing.

Sends (system prompt, conversation, available actions) to Gemini and gets back a
structured "which action, with what arguments" call. This uses Gemini's *native*
function-calling (forced with mode=ANY, so it must always call one of our actions,
never reply with plain chat text) rather than asking it to emit JSON as text — the
SDK hands back a typed `function_call`, so there's no "strip a ```json fence and hope
it's valid" step downstream.

Note: real browser-use's Gemini backend actually does NOT use native function-calling —
it uses response_schema/JSON mode instead, likely for a consistent story across many
providers (not every LLM API's native tool-calling looks the same, but "return JSON
matching this schema" is universal). We use native function-calling here per the
roadmap, since Gemini-only means we can lean on Gemini's own mechanism directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from google import genai
from google.genai import types
from pydantic import BaseModel

from messages import Message, SystemMessage, UserMessage
from run_logger import get_logger


@dataclass
class ActionCall:
    name: str
    args: dict


def build_tool(actions: dict[str, type[BaseModel]]) -> types.Tool:
    """One Gemini FunctionDeclaration per action, straight from its Pydantic schema."""
    declarations = [
        types.FunctionDeclaration(
            name=name,
            description=(model.__doc__ or name).strip(),
            parameters_json_schema=model.model_json_schema(),
        )
        for name, model in actions.items()
    ]
    get_logger().log(
        "gemini_client.py", "build_tool", "tool_schema_built",
        action_names=list(actions.keys()),
        declarations=[
            {"name": d.name, "description": d.description, "parameters_json_schema": d.parameters_json_schema}
            for d in declarations
        ],
    )
    return types.Tool(function_declarations=declarations)


def _to_content(message: Message) -> types.Content:
    role = "user" if isinstance(message, UserMessage) else "model"  # AssistantMessage -> "model"
    return types.Content(role=role, parts=[types.Part.from_text(text=message.content)])


def chat(
    messages: list[Message],
    actions: dict[str, type[BaseModel]],
    model: str = "gemini-2.5-flash",
) -> ActionCall:
    """Send the conversation + available actions to Gemini; force exactly one action back."""
    log = get_logger()
    system_instruction = next((m.content for m in messages if isinstance(m, SystemMessage)), None)
    contents = [_to_content(m) for m in messages if not isinstance(m, SystemMessage)]

    log.log(
        "gemini_client.py", "chat", "llm_request",
        model=model,
        system_instruction=system_instruction,
        messages=[{"role": type(m).__name__, "content": m.content} for m in messages],
        available_actions=list(actions.keys()),
    )

    client = genai.Client()
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[build_tool(actions)],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode=types.FunctionCallingConfigMode.ANY)
            ),
        ),
    )

    part = response.candidates[0].content.parts[0]
    raw_text = None
    if part.function_call is None:
        # Only worth the (SDK-warns-on-function-call-responses) cost of reading .text when
        # there's no function call — that's exactly the failure case where seeing what
        # Gemini said instead is genuinely useful for debugging.
        try:
            raw_text = response.text
        except Exception:
            raw_text = None
    log.log(
        "gemini_client.py", "chat", "llm_response",
        function_call_name=getattr(part.function_call, "name", None),
        function_call_args=dict(part.function_call.args) if part.function_call else None,
        raw_text=raw_text,
    )

    if part.function_call is None:
        raise ValueError(f"Gemini did not return a function call: {part!r}")
    return ActionCall(name=part.function_call.name, args=dict(part.function_call.args))


def parse_action(call: ActionCall, actions: dict[str, type[BaseModel]]) -> BaseModel:
    """Validate the raw args Gemini sent back into the actual Pydantic action model."""
    action = actions[call.name].model_validate(call.args)
    get_logger().log(
        "gemini_client.py", "parse_action", "action_validated",
        action_name=call.name, validated=action,
    )
    return action
