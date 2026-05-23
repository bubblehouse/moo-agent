"""Shared pytest fixtures for the moo-agent test suite."""

import os

import logfire
import pytest

from moo.agent.connection import MooSession

# ``Brain.__init__`` eagerly builds the PydanticAI Agent via ``make_agent``,
# and the Anthropic provider branch validates ``ANTHROPIC_API_KEY`` at
# construction time — so every Brain-touching test crashes in CI environments
# without the key. Tests never actually call the model (they mock
# ``call_llm`` or use ``TestModel``), so a dummy value is sufficient. The
# underlying eager-construction is a known design wart; see the polish-pass
# notes. Setdefault preserves a real key when one is present.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-unused")


@pytest.fixture(scope="session", autouse=True)
def _quiet_logfire():
    """
    Configure Logfire inert for tests.

    ``Brain._llm_cycle`` opens a ``logfire.span``; without a prior
    ``configure()`` Logfire warns once per process. ``send_to_logfire=False``
    ships nothing and ``console=False`` keeps test output clean.
    """
    logfire.configure(send_to_logfire=False, console=False)


@pytest.fixture
def thoughts() -> list[str]:
    """Capture list for ``on_thought`` callbacks. Pass ``thoughts.append`` as
    the callback; the list collects every emitted thought for assertions."""
    return []


@pytest.fixture
def session_and_received() -> tuple[MooSession, list[str]]:
    """A fresh ``MooSession`` with a list-capturing ``on_output``. Tests that
    drive ``data_received`` directly use this to assert what would have
    bubbled up to the brain."""
    received: list[str] = []
    return MooSession(on_output=received.append), received
