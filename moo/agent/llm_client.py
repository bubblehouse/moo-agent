"""
Provider-agnostic LLM client — Instructor-patched async clients returning a
validated ``AgentResponse``. See ``docs/source/explanation/agent-internals.md``
(The LLM Client) for provider selection and structured-output design.
"""

import os

import instructor

from moo.agent.response_model import AgentResponse


def make_client(llm_config):
    """Return an Instructor-patched async client for the configured provider."""
    if llm_config.provider == "bedrock":
        from anthropic import AsyncAnthropicBedrock  # pylint: disable=import-outside-toplevel

        return instructor.from_anthropic(
            AsyncAnthropicBedrock(aws_region=llm_config.aws_region),
            mode=instructor.Mode.ANTHROPIC_TOOLS,
        )
    if llm_config.provider == "lm_studio":
        from openai import AsyncOpenAI  # pylint: disable=import-outside-toplevel

        # JSON_SCHEMA mode — sends `response_format: {"type": "json_schema"}`,
        # which LM Studio enforces as a hard decoding constraint. (Plain JSON
        # mode sends `json_object`, which LM Studio rejects with a 400; tool
        # mode sends an object tool_choice, which it also rejects.)
        return instructor.from_openai(
            AsyncOpenAI(
                base_url=llm_config.base_url or "http://localhost:1234/v1",
                api_key="lm-studio",
            ),
            mode=instructor.Mode.JSON_SCHEMA,
        )
    from anthropic import AsyncAnthropic  # pylint: disable=import-outside-toplevel

    api_key = os.environ.get(llm_config.api_key_env, "")
    # ANTHROPIC_TOOLS (not JSON) so Instructor injects a tool rather than
    # appending to the system prompt — the cached system block stays intact.
    return instructor.from_anthropic(
        AsyncAnthropic(api_key=api_key),
        mode=instructor.Mode.ANTHROPIC_TOOLS,
    )


def _sampling_kwargs(temperature: float | None, top_p: float | None) -> dict:
    """Collect optional sampling kwargs, omitting any left as provider default."""
    kwargs: dict = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if top_p is not None:
        kwargs["top_p"] = top_p
    return kwargs


async def call_llm(
    client,
    llm_config,
    system: str,
    user_message: str,
    max_tokens: int,
    *,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    max_retries: int = 2,
) -> AgentResponse:
    """
    One structured LLM inference returning a validated ``AgentResponse``.

    Instructor handles the re-ask loop; an exhausted retry budget surfaces as
    ``instructor.exceptions.InstructorRetryException`` for the caller to map
    onto stall recovery.
    """
    if llm_config.provider == "lm_studio":
        extra_body: dict = {
            "enable_thinking": False,
            "cache_type_k": "q8_0",
            "cache_type_v": "q8_0",
        }
        if top_k is not None:
            extra_body["top_k"] = top_k
        return await client.chat.completions.create(
            model=llm_config.model,
            response_model=AgentResponse,
            max_retries=max_retries,
            max_tokens=max_tokens,
            extra_body=extra_body,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            **_sampling_kwargs(temperature, top_p),
        )

    # Anthropic / Bedrock — cache the system block as an ephemeral prefix
    # (5 min TTL). For chained workers cycling within one pass, the hit rate
    # justifies the 1.25x first-call write cost.
    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    kwargs = _sampling_kwargs(temperature, top_p)
    if top_k is not None:
        kwargs["top_k"] = top_k
    return await client.messages.create(
        model=llm_config.model,
        response_model=AgentResponse,
        max_retries=max_retries,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=[{"role": "user", "content": user_message}],
        **kwargs,
    )


async def summarize(client, llm_config, system: str, content: str, max_tokens: int) -> str:
    """Plain-text completion for window summarization (no structured model)."""
    raw = getattr(client, "client", client)
    if llm_config.provider == "lm_studio":
        resp = await raw.chat.completions.create(
            model=llm_config.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        )
        return (resp.choices[0].message.content or "").strip()
    resp = await raw.messages.create(
        model=llm_config.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    return " ".join(b.text for b in resp.content if b.type == "text").strip()
