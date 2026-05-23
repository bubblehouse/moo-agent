"""
Provider-agnostic LLM client built on PydanticAI. ``make_agent`` constructs one
``Agent`` per session; ``call_llm`` runs it and returns a validated
``AgentResponse``. See ``docs/source/explanation/agent-internals.md`` (The LLM
Client) for provider selection and structured-output design.
"""

import os
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from moo.agent.response_model import AgentResponse

# ``BrainDeps`` and ``ALL_TOOLS`` are imported lazily inside ``make_agent`` to
# avoid the brain → llm_client → agent_tools → brain.deps → brain cycle that
# Python's package-init evaluation order would otherwise create.
if TYPE_CHECKING:
    from moo.agent.brain.deps import BrainDeps  # noqa: F401


def _patch_reasoning_content(client):
    """
    Promote ``reasoning_content`` into ``content`` when LM Studio leaves the
    latter empty.

    Under ``response_format: json_schema``, thinking models (Qwen3.x on the MLX
    engine) route the schema-constrained JSON into ``reasoning_content`` and
    leave ``content`` empty. PydanticAI reads ``content``, so without this shim
    the structured-output parse sees nothing.
    """
    original = client.chat.completions.create

    async def create(*args, **kwargs):
        response = await original(*args, **kwargs)
        for choice in getattr(response, "choices", None) or []:
            message = getattr(choice, "message", None)
            if message is not None and not (getattr(message, "content", None) or "").strip():
                reasoning = getattr(message, "reasoning_content", None)
                if reasoning and reasoning.strip():
                    message.content = reasoning
        return response

    client.chat.completions.create = create
    return client


def make_agent(
    llm_config,
    system_prompt: str,
    retries: int = 2,
    name: str | None = None,
    tool_names: list[str] | None = None,
) -> Agent:
    """
    Build the per-session PydanticAI ``Agent`` for the configured provider.

    The Agent holds the (static) system prompt, the ``AgentResponse`` output
    type, ``BrainDeps`` as the per-run dependencies, and the per-agent tool
    set. ``tool_names=None`` registers every tool; passing a list of names
    filters ``ALL_TOOLS`` to that whitelist (plus the always-on
    ``raw``/``respond`` system tools). Restoring this whitelist matters
    because each tool's JSON schema lands in the system prompt's tool block
    — 33 tools per agent floors the prompt at ~14k tokens.

    Tool-based structured output is the default for every provider — the LM
    Studio spike (docs/specs/pydantic-ai-stage-2.md appendix) showed that
    ``NativeOutput``'s JSON-schema constrained decoding suppresses tool calls
    on ``qwen3.5-9b-mlx``. Brain holds one Agent for the session so LM Studio
    keeps its KV cache warm across cycles.

    ``name`` is the PydanticAI agent identifier surfaced in Logfire's Agents
    view. Pass the worker name (``mason``, ``tinker``, etc.) so traces group
    by agent rather than showing a single unnamed bucket.
    """
    from moo.agent.agent_tools import select_tools  # pylint: disable=import-outside-toplevel
    from moo.agent.brain.deps import BrainDeps  # pylint: disable=import-outside-toplevel

    if llm_config.provider == "lm_studio":
        from openai import AsyncOpenAI  # pylint: disable=import-outside-toplevel
        from pydantic_ai.models.openai import OpenAIChatModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.openai import OpenAIProvider  # pylint: disable=import-outside-toplevel

        client = _patch_reasoning_content(
            AsyncOpenAI(base_url=llm_config.base_url or "http://localhost:1234/v1", api_key="lm-studio")
        )
        model = OpenAIChatModel(llm_config.model, provider=OpenAIProvider(openai_client=client))
    elif llm_config.provider == "bedrock":
        from pydantic_ai.models.bedrock import BedrockConverseModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.bedrock import BedrockProvider  # pylint: disable=import-outside-toplevel

        model = BedrockConverseModel(llm_config.model, provider=BedrockProvider(region_name=llm_config.aws_region))
    else:
        from pydantic_ai.models.anthropic import AnthropicModel  # pylint: disable=import-outside-toplevel
        from pydantic_ai.providers.anthropic import AnthropicProvider  # pylint: disable=import-outside-toplevel

        api_key = os.environ.get(llm_config.api_key_env, "")
        model = AnthropicModel(llm_config.model, provider=AnthropicProvider(api_key=api_key))

    return Agent(
        model,
        output_type=AgentResponse,
        deps_type=BrainDeps,
        tools=select_tools(tool_names),
        system_prompt=system_prompt,
        retries=retries,
        name=name,
    )


def _model_settings(
    llm_config,
    max_tokens: int,
    temperature: float | None,
    top_p: float | None,
    top_k: int | None,
    repeat_penalty: float | None,
    min_p: float | None,
) -> ModelSettings:
    """Build the per-call ``ModelSettings`` from the agent's sampling config."""
    settings: ModelSettings = {"max_tokens": max_tokens}
    if temperature is not None:
        settings["temperature"] = temperature
    if top_p is not None:
        settings["top_p"] = top_p
    if top_k is not None:
        settings["top_k"] = top_k
    if llm_config.provider == "lm_studio":
        # repeat_penalty / min_p are the levers against token-loop degeneration
        # under JSON-schema constrained decoding. reasoning_effort and cache_type
        # are LM Studio engine flags. All ride in extra_body.
        extra: dict = {"reasoning_effort": "none", "cache_type_k": "q8_0", "cache_type_v": "q8_0"}
        if repeat_penalty is not None:
            extra["repeat_penalty"] = repeat_penalty
        if min_p is not None:
            extra["min_p"] = min_p
        settings["extra_body"] = extra
    return settings


async def call_llm(
    agent: Agent,
    llm_config,
    user_message: str,
    max_tokens: int,
    *,
    deps: "BrainDeps",  # string forward ref — see module docstring on lazy import
    tool_calls_limit: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    repeat_penalty: float | None = None,
    min_p: float | None = None,
) -> tuple[AgentResponse, int]:
    """
    Run one structured inference + tool loop. Return the validated
    ``AgentResponse`` and the count of tool calls PydanticAI dispatched
    across the multi-turn run (for Logfire span attribution).

    PydanticAI handles the re-ask loop and the tool dispatch; an exhausted
    retry budget surfaces as ``pydantic_ai.exceptions.UnexpectedModelBehavior``
    and a tool-call-cap breach surfaces as
    ``pydantic_ai.exceptions.UsageLimitExceeded`` — both are left for the
    caller to map onto stall recovery.

    ``tool_calls_limit`` (when set) bounds the number of successful tool
    invocations inside this single ``agent.run()``; PydanticAI's default has
    no such cap so a degenerate model can call ``respond()`` indefinitely
    within one cycle. ``deps`` is the per-cycle ``BrainDeps`` passed to every
    ``@agent.tool`` via ``RunContext``.
    """
    settings = _model_settings(llm_config, max_tokens, temperature, top_p, top_k, repeat_penalty, min_p)
    usage_limits = UsageLimits(tool_calls_limit=tool_calls_limit) if tool_calls_limit is not None else None
    result = await agent.run(user_message, model_settings=settings, deps=deps, usage_limits=usage_limits)
    tool_calls = getattr(result.usage, "tool_calls", 0) or 0
    return result.output, tool_calls
