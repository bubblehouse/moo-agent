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


def _lm_studio_extra_body(
    top_k: int | None,
    repeat_penalty: float | None,
    min_p: float | None,
    **base,
) -> dict:
    """
    Build LM Studio's ``extra_body``: base flags plus any non-default sampler.

    ``repeat_penalty`` and ``min_p`` are the levers against token-loop
    degeneration under JSON_SCHEMA constrained decoding — top_k/top_p alone
    cannot break a repetition once it starts.
    """
    body: dict = dict(base)
    if top_k is not None:
        body["top_k"] = top_k
    if repeat_penalty is not None:
        body["repeat_penalty"] = repeat_penalty
    if min_p is not None:
        body["min_p"] = min_p
    return body


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
    repeat_penalty: float | None = None,
    min_p: float | None = None,
    max_retries: int = 2,
) -> AgentResponse:
    """
    One structured LLM inference returning a validated ``AgentResponse``.

    Instructor handles the re-ask loop; an exhausted retry budget surfaces as
    ``instructor.exceptions.InstructorRetryException`` for the caller to map
    onto stall recovery.
    """
    if llm_config.provider == "lm_studio":
        extra_body = _lm_studio_extra_body(
            top_k,
            repeat_penalty,
            min_p,
            reasoning_effort="none",
            cache_type_k="q8_0",
            cache_type_v="q8_0",
        )
        # Bypass Instructor's parse for LM Studio: thinking models (Qwen3.x)
        # route the structured JSON into `reasoning_content` and leave
        # `content` empty. `reasoning_effort` can suppress that on the GGUF
        # engine but NOT on MLX (the model exposes no reasoning KVs). So send
        # the JSON-schema response_format ourselves, then read whichever field
        # actually carries the payload and validate it.
        raw = getattr(client, "client", client)
        resp = await raw.chat.completions.create(
            model=llm_config.model,
            max_tokens=max_tokens,
            extra_body=extra_body,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "AgentResponse",
                    "schema": AgentResponse.model_json_schema(),
                    "strict": True,
                },
            },
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            **_sampling_kwargs(temperature, top_p),
        )
        message = resp.choices[0].message
        text = (message.content or "").strip()
        if not text:
            text = (getattr(message, "reasoning_content", "") or "").strip()
        return AgentResponse.model_validate_json(text)

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


async def summarize(
    client,
    llm_config,
    system: str,
    content: str,
    max_tokens: int,
    *,
    temperature: float | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    repeat_penalty: float | None = None,
    min_p: float | None = None,
) -> str:
    """
    Plain-text completion for window summarization (no structured model).

    Takes the same sampling params as ``call_llm``: without them, the
    summarize call falls back to LM Studio's stock sampling, which makes
    Gemma degenerate into token-repetition loops. A degenerated summary is
    then stored as ``memory_summary`` and re-injected into every later
    prompt, poisoning the whole session.
    """
    raw = getattr(client, "client", client)
    if llm_config.provider == "lm_studio":
        extra_body = _lm_studio_extra_body(top_k, repeat_penalty, min_p, reasoning_effort="none")
        resp = await raw.chat.completions.create(
            model=llm_config.model,
            max_tokens=max_tokens,
            extra_body=extra_body,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            **_sampling_kwargs(temperature, top_p),
        )
        return (resp.choices[0].message.content or "").strip()
    kwargs = _sampling_kwargs(temperature, top_p)
    if top_k is not None:
        kwargs["top_k"] = top_k
    resp = await raw.messages.create(
        model=llm_config.model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        **kwargs,
    )
    return " ".join(b.text for b in resp.content if b.type == "text").strip()
