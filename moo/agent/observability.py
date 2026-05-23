"""
Logfire observability setup. Instruments the Anthropic and OpenAI SDK clients
so every LLM call — including Instructor's re-ask retries — is traced with
token usage, latency, and cost. See ``docs/source/explanation/agent-internals.md``
(The LLM Client).
"""

import os

import logfire


def setup_observability(service_name: str) -> None:
    """
    Configure Logfire and instrument the LLM SDK clients.

    ``send_to_logfire="if-token-present"`` ships traces only when LOGFIRE_TOKEN
    is set; without it the call is a local no-op, so CI and token-less dev runs
    are unaffected. ``console=False`` keeps Logfire off stdout — moo-agent runs a
    prompt_toolkit TUI that console output would corrupt.

    The Logfire environment defaults to ``local``; override it with the
    ``LOGFIRE_ENVIRONMENT`` env var (e.g. ``staging``) for non-local deploys.

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
    logfire.instrument_anthropic()
    logfire.instrument_openai()
