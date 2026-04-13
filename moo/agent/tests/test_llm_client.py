"""
Tests for moo/agent/llm_client.py.

Covers:
  - make_client: returns the right SDK instance for each provider
  - parse_lm_studio_tool_calls: pure, table-driven against the four
    fallback strategies and their priority ordering
  - call_llm: provider branches via AsyncMock; normalizes text and
    structured tool_calls regardless of provider
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from moo.agent.llm_client import call_llm, make_client, parse_lm_studio_tool_calls
from moo.agent.tools import BUILDER_TOOLS, LLMResponse


# --- parse_lm_studio_tool_calls (additional coverage beyond test_brain.py) ---


def test_parse_xml_tool_call_parameters_alias():
    """Fallback 1 accepts either ``arguments`` or ``parameters`` key."""
    text = '<tool_call>{"name": "dig", "parameters": {"direction": "east"}}</tool_call>'
    result = parse_lm_studio_tool_calls(text, set())
    assert result == [("dig", {"direction": "east"})]


def test_parse_xml_tool_call_malformed_json_skipped():
    """Malformed JSON inside <tool_call> is silently skipped."""
    text = '<tool_call>{"name": "dig", bad json}</tool_call>'
    result = parse_lm_studio_tool_calls(text, set())
    assert not result


def test_parse_xml_tool_call_missing_name_skipped():
    """<tool_call> without a name is skipped."""
    text = '<tool_call>{"arguments": {"direction": "north"}}</tool_call>'
    result = parse_lm_studio_tool_calls(text, set())
    assert not result


def test_parse_multiple_xml_tool_calls():
    """Multiple <tool_call> blocks are all captured in order."""
    text = (
        '<tool_call>{"name": "dig", "arguments": {"direction": "north"}}</tool_call>\n'
        '<tool_call>{"name": "burrow", "arguments": {"direction": "south"}}</tool_call>'
    )
    result = parse_lm_studio_tool_calls(text, set())
    assert len(result) == 2
    assert result[0][0] == "dig"
    assert result[1][0] == "burrow"


def test_parse_empty_text():
    assert not parse_lm_studio_tool_calls("", set())


def test_parse_plain_text_no_tool_calls():
    """Plain text with no tool call syntax returns empty list."""
    text = "I should look around first before taking any action."
    assert not parse_lm_studio_tool_calls(text, set())


def test_parse_bare_function_requires_known_names():
    """Fallback 4 only fires when known_names contains the called name."""
    text = "dig(direction='north', room_name='Foo')"
    assert not parse_lm_studio_tool_calls(text, set())
    result = parse_lm_studio_tool_calls(text, {"dig"})
    assert len(result) == 1
    assert result[0][0] == "dig"


def test_parse_call_tag_takes_priority_over_bare_function():
    """Fallback 2 (call tag) runs before fallback 4 (bare function)."""
    text = "<call:dig(direction='north')>"
    result = parse_lm_studio_tool_calls(text, {"dig", "burrow"})
    assert result == [("dig", {"direction": "north"})]


# --- make_client ---


def _llm_config(provider, **extra):
    base = dict(
        provider=provider,
        model="test-model",
        max_tokens=200,
        api_key_env="TEST_KEY",
        aws_region="us-east-1",
        base_url=None,
    )
    base.update(extra)
    return SimpleNamespace(**base)


def test_make_client_lm_studio():
    from openai import AsyncOpenAI

    cfg = _llm_config("lm_studio", base_url="http://localhost:1234/v1")
    client = make_client(cfg)
    assert isinstance(client, AsyncOpenAI)


def test_make_client_lm_studio_default_base_url():
    from openai import AsyncOpenAI

    cfg = _llm_config("lm_studio")
    client = make_client(cfg)
    assert isinstance(client, AsyncOpenAI)


def test_make_client_anthropic(monkeypatch):
    from anthropic import AsyncAnthropic

    monkeypatch.setenv("TEST_KEY", "fake-key")
    cfg = _llm_config("anthropic")
    client = make_client(cfg)
    assert isinstance(client, AsyncAnthropic)


def test_make_client_anthropic_missing_env(monkeypatch):
    """Missing env var is tolerated — the SDK is constructed with an empty key."""
    from anthropic import AsyncAnthropic

    monkeypatch.delenv("TEST_KEY", raising=False)
    cfg = _llm_config("anthropic")
    client = make_client(cfg)
    assert isinstance(client, AsyncAnthropic)


# --- call_llm ---


def _mock_lm_studio_response(*, text="", openai_tool_calls=None):
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = openai_tool_calls or []
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_openai_tool_call(name, args):
    tc = MagicMock()
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def test_call_llm_lm_studio_text_only():
    cfg = _llm_config("lm_studio")
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_lm_studio_response(text="GOAL: look\nCOMMAND: look"))

    result = asyncio.run(call_llm(client, cfg, [], "system", "user", 200))
    assert isinstance(result, LLMResponse)
    assert "GOAL: look" in result.text
    assert result.tool_calls == []


def test_call_llm_lm_studio_structured_tool_calls():
    cfg = _llm_config("lm_studio")
    tc = _make_openai_tool_call("dig", {"direction": "north"})
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_lm_studio_response(text="", openai_tool_calls=[tc]))

    tools = list(BUILDER_TOOLS)
    result = asyncio.run(call_llm(client, cfg, tools, "system", "user", 200))
    assert result.tool_calls == [("dig", {"direction": "north"})]


def test_call_llm_lm_studio_text_fallback_tool_call():
    """When no structured tool_calls, plain-text fallbacks run."""
    cfg = _llm_config("lm_studio")
    text = '<tool_call>{"name": "dig", "arguments": {"direction": "east"}}</tool_call>'
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_lm_studio_response(text=text))

    tools = list(BUILDER_TOOLS)
    result = asyncio.run(call_llm(client, cfg, tools, "system", "user", 200))
    assert result.tool_calls == [("dig", {"direction": "east"})]


def test_call_llm_lm_studio_strips_special_tokens():
    """Harmony/ChatML tokens are scrubbed from text output."""
    cfg = _llm_config("lm_studio")
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_mock_lm_studio_response(text="<|channel|>thought<|endoftext|>GOAL: look")
    )

    result = asyncio.run(call_llm(client, cfg, [], "system", "user", 200))
    assert "<|" not in result.text
    assert "GOAL: look" in result.text


def test_call_llm_lm_studio_malformed_tool_args_default_to_empty_dict():
    cfg = _llm_config("lm_studio")
    tc = MagicMock()
    tc.function = MagicMock()
    tc.function.name = "dig"
    tc.function.arguments = "not valid json"
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_mock_lm_studio_response(text="", openai_tool_calls=[tc]))

    tools = list(BUILDER_TOOLS)
    result = asyncio.run(call_llm(client, cfg, tools, "system", "user", 200))
    assert result.tool_calls == [("dig", {})]


def _mock_anthropic_response(*, text_parts=None, tool_uses=None):
    blocks = []
    for t in text_parts or []:
        b = MagicMock()
        b.type = "text"
        b.text = t
        blocks.append(b)
    for name, inp in tool_uses or []:
        b = MagicMock()
        b.type = "tool_use"
        b.name = name
        b.input = inp
        blocks.append(b)
    resp = MagicMock()
    resp.content = blocks
    return resp


def test_call_llm_anthropic_text_only():
    cfg = _llm_config("anthropic")
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(text_parts=["GOAL: look", "COMMAND: look"])
    )

    result = asyncio.run(call_llm(client, cfg, [], "system", "user", 200))
    assert "GOAL: look" in result.text
    assert result.tool_calls == []


def test_call_llm_anthropic_with_tool_use():
    cfg = _llm_config("anthropic")
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(
            text_parts=["thinking"],
            tool_uses=[("dig", {"direction": "west"})],
        )
    )

    tools = list(BUILDER_TOOLS)
    result = asyncio.run(call_llm(client, cfg, tools, "system", "user", 200))
    assert result.tool_calls == [("dig", {"direction": "west"})]
    assert "thinking" in result.text


def test_call_llm_anthropic_strips_special_tokens():
    cfg = _llm_config("anthropic")
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        return_value=_mock_anthropic_response(text_parts=["<|channel|>thought", "GOAL: look"])
    )

    result = asyncio.run(call_llm(client, cfg, [], "system", "user", 200))
    assert "<|" not in result.text
