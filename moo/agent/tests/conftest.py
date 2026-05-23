"""Shared pytest fixtures for the moo-agent test suite."""

import logfire
import pytest


@pytest.fixture(scope="session", autouse=True)
def _quiet_logfire():
    """
    Configure Logfire inert for tests.

    ``Brain._llm_cycle`` opens a ``logfire.span``; without a prior
    ``configure()`` Logfire warns once per process. ``send_to_logfire=False``
    ships nothing and ``console=False`` keeps test output clean.
    """
    logfire.configure(send_to_logfire=False, console=False)
