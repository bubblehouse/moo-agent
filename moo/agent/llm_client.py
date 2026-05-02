"""
Provider-agnostic LLM client helpers — ``make_client``,
``parse_lm_studio_tool_calls``, ``call_llm``. See
``docs/source/explanation/agent-internals.md`` (The LLM Client) for the
provider selection, scrubbing, and fallback design.
"""

import json
import os
import re

from anthropic import AsyncAnthropic, AsyncAnthropicBedrock

from moo.agent.tools import LLMResponse, ToolSpec, parse_tool_line


_XML_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_CALL_TAG_RE = re.compile(r"^<call:(\w+)\(([^>]*)\)>$")
_CALL_TAG_ARG_RE = re.compile(r"""(\w+)=['"]([^'"]*)['"]\s*,?\s*""")

# Strip Harmony/ChatML tokens from LLM output. See agent-internals:
# Special-token scrubbing.
_SPECIAL_TOKEN_RE = re.compile(r"<\|[^|>]+\|?>|<[A-Za-z_]\w*\|>")


def make_client(llm_config):
    """Return an API client for the configured LLM provider."""
    if llm_config.provider == "bedrock":
        return AsyncAnthropicBedrock(aws_region=llm_config.aws_region)
    if llm_config.provider == "lm_studio":
        from openai import AsyncOpenAI  # pylint: disable=import-outside-toplevel

        return AsyncOpenAI(
            base_url=llm_config.base_url or "http://localhost:1234/v1",
            api_key="lm-studio",
        )
    api_key = os.environ.get(llm_config.api_key_env, "")
    return AsyncAnthropic(api_key=api_key)


def parse_lm_studio_tool_calls(text: str, known_names: set[str]) -> list[tuple[str, dict]]:
    """
    Pure four-strategy fallback parser. See agent-internals: The LLM Client
    for the strategy list (XML, call: tag, TOOL: line, bare call).
    """
    tool_calls: list[tuple[str, dict]] = []

    for m in _XML_TOOL_CALL_RE.finditer(text):
        try:
            obj = json.loads(m.group(1))
            name = obj.get("name") or ""
            args = obj.get("arguments") or obj.get("parameters") or {}
            if name:
                tool_calls.append((name, args))
        except Exception:  # pylint: disable=broad-exception-caught
            pass
    if not tool_calls:
        for line in text.splitlines():
            tag_m = _CALL_TAG_RE.match(line.strip())
            if tag_m is not None:
                name = tag_m.group(1)
                args = {k: v for k, v in _CALL_TAG_ARG_RE.findall(tag_m.group(2))}
                tool_calls.append((name, args))
    if not tool_calls:
        for line in text.splitlines():
            parsed = parse_tool_line(line)
            if parsed:
                tool_calls.append(parsed)
    if not tool_calls:
        for line in text.splitlines():
            parsed = parse_tool_line(line, known_names=known_names)
            if parsed:
                tool_calls.append(parsed)

    return tool_calls


async def call_llm(
    client,
    llm_config,
    tools: list[ToolSpec],
    system: str,
    user_message: str,
    max_tokens: int,
    temperature: float | None = None,
) -> LLMResponse:
    """One LLM inference call returning a normalized ``LLMResponse``."""
    if llm_config.provider == "lm_studio":
        kwargs: dict = {}
        if tools:
            kwargs["tools"] = [t.to_openai_schema() for t in tools]
            kwargs["tool_choice"] = "auto"
        if temperature is not None:
            kwargs["temperature"] = temperature
        resp = await client.chat.completions.create(
            model=llm_config.model,
            max_tokens=max_tokens,
            extra_body={
                "enable_thinking": False,
                "cache_type_k": "q8_0",
                "cache_type_v": "q8_0",
            },
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            **kwargs,
        )
        msg = resp.choices[0].message
        text = (msg.content or "").replace("<|endoftext|>", "")
        text = _SPECIAL_TOKEN_RE.sub("", text).strip()
        tool_calls: list[tuple[str, dict]] = []
        if tools and msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except Exception:  # pylint: disable=broad-exception-caught
                    args = {}
                tool_calls.append((tc.function.name, args))
        elif tools and text:
            known_names = {t.name for t in tools}
            tool_calls = parse_lm_studio_tool_calls(text, known_names)
        return LLMResponse(text=text, tool_calls=tool_calls)

    # Anthropic / Bedrock path
    from anthropic import NOT_GIVEN  # pylint: disable=import-outside-toplevel

    tools_schema = [t.to_anthropic_schema() for t in tools] if tools else NOT_GIVEN
    resp = await client.messages.create(
        model=llm_config.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        tools=tools_schema,
    )
    text_parts = [b.text for b in resp.content if b.type == "text"]
    tool_calls = [(b.name, b.input) for b in resp.content if b.type == "tool_use"]
    joined = _SPECIAL_TOKEN_RE.sub("", " ".join(text_parts))
    return LLMResponse(text=joined, tool_calls=tool_calls)
