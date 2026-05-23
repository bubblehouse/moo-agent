"""
Tests for moo/agent/llm_client.py.

Covers:
  - make_agent: returns a PydanticAI Agent per provider
  - call_llm: runs the agent and returns the validated AgentResponse
  - _model_settings: provider-specific sampling-kwarg assembly
  - _patch_reasoning_content: LM Studio reasoning_content -> content shim
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from moo.agent.brain.deps import BrainDeps
from moo.agent.brain.state import BrainState
from moo.agent.llm_client import _model_settings, _patch_reasoning_content, call_llm, make_agent
from moo.agent.response_model import AgentResponse


def _stub_deps() -> BrainDeps:
    """Minimal BrainDeps for call_llm — the TestModel agent never invokes tools."""
    return BrainDeps(
        connection=SimpleNamespace(send=lambda _c: None),  # type: ignore[arg-type]
        limiter=SimpleNamespace(wait=lambda: None),  # type: ignore[arg-type]
        soul_name="tester",
        state=BrainState(),
        on_thought=lambda _t: None,
        on_window_append=lambda _l: None,
    )


def _llm_config(provider, **extra):
    base = dict(
        provider=provider,
        model="test-model",
        api_key_env="TEST_KEY",
        aws_region="us-east-1",
        base_url=None,
    )
    base.update(extra)
    return SimpleNamespace(**base)


# --- make_agent ---


def test_make_agent_lm_studio():
    agent = make_agent(_llm_config("lm_studio", base_url="http://localhost:1234/v1"), "system")
    assert isinstance(agent, Agent)


def test_make_agent_lm_studio_default_base_url():
    agent = make_agent(_llm_config("lm_studio"), "system")
    assert isinstance(agent, Agent)


def test_make_agent_anthropic(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "fake-key")
    agent = make_agent(_llm_config("anthropic"), "system")
    assert isinstance(agent, Agent)


# --- call_llm ---


def test_call_llm_returns_agent_response_and_tool_calls():
    """call_llm runs the agent and returns (validated AgentResponse, tool_calls)."""
    model = TestModel(custom_output_args={"goal": "look around"})
    agent = Agent(model, output_type=AgentResponse, system_prompt="system")

    output, tool_calls = asyncio.run(call_llm(agent, _llm_config("anthropic"), "user message", 200, deps=_stub_deps()))
    assert isinstance(output, AgentResponse)
    assert output.goal == "look around"
    assert isinstance(tool_calls, int)


def test_call_llm_lm_studio_config():
    """The lm_studio config branch still produces a validated response."""
    model = TestModel(custom_output_args={"goal": "from lm studio"})
    agent = Agent(model, output_type=AgentResponse, system_prompt="system")

    output, _tc = asyncio.run(call_llm(agent, _llm_config("lm_studio"), "user message", 200, deps=_stub_deps()))
    assert output.goal == "from lm studio"


# --- _model_settings ---


def test_model_settings_lm_studio_sampling():
    """LM Studio gets repeat_penalty/min_p/reasoning_effort in extra_body."""
    settings = _model_settings(_llm_config("lm_studio"), 256, 0.7, 0.8, 20, 1.05, 0.03)
    assert settings["max_tokens"] == 256
    assert settings["temperature"] == 0.7
    assert settings["top_p"] == 0.8
    assert settings["top_k"] == 20
    assert settings["extra_body"]["repeat_penalty"] == 1.05
    assert settings["extra_body"]["min_p"] == 0.03
    assert settings["extra_body"]["reasoning_effort"] == "none"


def test_model_settings_anthropic_no_extra_body():
    """Non-lm_studio providers omit extra_body and unset sampling params."""
    settings = _model_settings(_llm_config("anthropic"), 256, 0.5, None, 40, None, None)
    assert settings["max_tokens"] == 256
    assert settings["temperature"] == 0.5
    assert settings["top_k"] == 40
    assert "top_p" not in settings
    assert "extra_body" not in settings


# --- _patch_reasoning_content ---


def _completion(content="", reasoning_content=""):
    """A raw ChatCompletion shape — what LM Studio's OpenAI endpoint returns."""
    message = SimpleNamespace(content=content, reasoning_content=reasoning_content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_patch_reasoning_content_promotes_when_content_empty():
    """When content is empty, reasoning_content is copied into content."""
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_completion(reasoning_content='{"goal":"x"}'))
    _patch_reasoning_content(client)

    out = asyncio.run(client.chat.completions.create())
    assert out.choices[0].message.content == '{"goal":"x"}'


def test_patch_reasoning_content_leaves_content_when_present():
    """When content is already populated, reasoning_content is ignored."""
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_completion(content='{"goal":"real"}', reasoning_content="noise")
    )
    _patch_reasoning_content(client)

    out = asyncio.run(client.chat.completions.create())
    assert out.choices[0].message.content == '{"goal":"real"}'
