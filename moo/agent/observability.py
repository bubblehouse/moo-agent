"""
Logfire observability setup. Instruments the PydanticAI agent loop plus the
provider's underlying SDK client (Anthropic or OpenAI) so every LLM call —
including PydanticAI's structured-output re-asks — is traced with latency
and the agent.run span tree. See ``docs/source/explanation/agent-internals.md``
(The LLM Client).
"""

import os

import logfire


def setup_observability(service_name: str, provider: str = "") -> None:
    """
    Configure Logfire and instrument the LLM SDK clients.

    ``send_to_logfire="if-token-present"`` ships traces only when LOGFIRE_TOKEN
    is set; without it the call is a local no-op, so CI and token-less dev runs
    are unaffected. ``console=False`` keeps Logfire off stdout — moo-agent runs a
    prompt_toolkit TUI that console output would corrupt.

    The Logfire environment defaults to ``local``; override it with the
    ``LOGFIRE_ENVIRONMENT`` env var (e.g. ``staging``) for non-local deploys.

    ``provider`` gates which SDK client instrumentation runs. ``lm_studio``
    uses OpenAI under the hood; ``anthropic`` (the default Claude path) uses
    the Anthropic SDK; ``bedrock`` rides on the bedrock SDK and needs neither.
    Empty / unknown provider strings instrument both as a safe fallback.

    Must run before any LLM client is constructed: ``instrument_*`` patches the
    SDK classes globally.
    """
    logfire.configure(
        send_to_logfire="if-token-present",
        console=False,
        service_name=service_name,
        environment=os.getenv("LOGFIRE_ENVIRONMENT", "local"),
    )
    logfire.instrument_pydantic_ai()
    if provider in ("anthropic", ""):
        logfire.instrument_anthropic()
    if provider in ("lm_studio", ""):
        logfire.instrument_openai()
