"""
Tests for moo/agent/llm_client.py.

Covers:
  - make_client: returns an Instructor-patched async client per provider
  - call_llm: provider branches, returns the validated AgentResponse, and
    forwards sampling kwargs to the underlying client
  - summarize: plain-text completion path for window summarization
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import instructor

from moo.agent.llm_client import call_llm, make_client, summarize
from moo.agent.response_model import AgentResponse


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


# --- make_client ---


def test_make_client_lm_studio():
    client = make_client(_llm_config("lm_studio", base_url="http://localhost:1234/v1"))
    assert isinstance(client, instructor.AsyncInstructor)


def test_make_client_lm_studio_default_base_url():
    client = make_client(_llm_config("lm_studio"))
    assert isinstance(client, instructor.AsyncInstructor)


def test_make_client_anthropic(monkeypatch):
    monkeypatch.setenv("TEST_KEY", "fake-key")
    client = make_client(_llm_config("anthropic"))
    assert isinstance(client, instructor.AsyncInstructor)


def test_make_client_anthropic_missing_env(monkeypatch):
    """Missing env var is tolerated — the SDK is constructed with an empty key."""
    monkeypatch.delenv("TEST_KEY", raising=False)
    client = make_client(_llm_config("anthropic"))
    assert isinstance(client, instructor.AsyncInstructor)


# --- call_llm ---


def _lm_studio_client(response):
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def _anthropic_client(response):
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def test_call_llm_lm_studio_returns_agent_response():
    cfg = _llm_config("lm_studio")
    expected = AgentResponse(goal="look around", actions=[])
    client = _lm_studio_client(expected)

    result = asyncio.run(call_llm(client, cfg, "system", "user", 200))
    assert result is expected

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_model"] is AgentResponse
    assert kwargs["model"] == "test-model"


def test_call_llm_lm_studio_forwards_sampling():
    cfg = _llm_config("lm_studio")
    client = _lm_studio_client(AgentResponse(goal="g"))

    asyncio.run(call_llm(client, cfg, "system", "user", 200, temperature=1.0, top_p=0.95, top_k=64, max_retries=3))
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 1.0
    assert kwargs["top_p"] == 0.95
    assert kwargs["extra_body"]["top_k"] == 64
    assert kwargs["max_retries"] == 3


def test_call_llm_anthropic_returns_agent_response():
    cfg = _llm_config("anthropic")
    expected = AgentResponse(goal="look around")
    client = _anthropic_client(expected)

    result = asyncio.run(call_llm(client, cfg, "system", "user", 200))
    assert result is expected


def test_call_llm_anthropic_caches_system_block():
    """The system block carries an ephemeral cache_control marker."""
    cfg = _llm_config("anthropic")
    client = _anthropic_client(AgentResponse(goal="g"))

    asyncio.run(call_llm(client, cfg, "the system prompt", "user", 200, top_k=40))
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["response_model"] is AgentResponse
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["system"][0]["text"] == "the system prompt"
    assert kwargs["top_k"] == 40


# --- summarize ---


def test_summarize_lm_studio():
    cfg = _llm_config("lm_studio")
    msg = MagicMock()
    msg.content = "  A concise summary.  "
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    client = _lm_studio_client(resp)
    client.client = client  # patched clients expose the raw SDK at .client

    result = asyncio.run(summarize(client, cfg, "summarize this", "log text", 150))
    assert result == "A concise summary."


def test_summarize_anthropic():
    cfg = _llm_config("anthropic")
    block = MagicMock()
    block.type = "text"
    block.text = "A concise summary."
    resp = MagicMock()
    resp.content = [block]
    client = _anthropic_client(resp)
    client.client = client  # patched clients expose the raw SDK at .client

    result = asyncio.run(summarize(client, cfg, "summarize this", "log text", 150))
    assert result == "A concise summary."
