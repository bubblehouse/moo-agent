#!moo verb initialize --on "Container"
# pylint: disable=undefined-variable
"""Containers chain to Thing's initialize (move + write).

``passthrough()`` invokes the next-up parent's same-named verb (see
moo/AGENTS.md), which grants both ``move`` and ``write`` on the Object.
Containers add no extra grants — open/close mutations of the ``open``
property are covered by ``write`` from Thing.
"""

passthrough()  # Thing/initialize: move + write
