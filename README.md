# moo-agent

Autonomous AI agent client for [DjangoMOO](https://gitlab.com/bubblehouse/django-moo)
servers, plus the collected agentic AI work built around it.

`moo-agent` started as a CLI that drives an AI persona over SSH against a running
DjangoMOO server, reading personality and operational rules from a `SOUL.md` file
with runtime learning via `SOUL.patch.md`. Backends include Anthropic, AWS Bedrock,
and local LM Studio models.

Over time this repo has grown into the home for everything AI-adjacent in the
DjangoMOO ecosystem: the agent runtime, pre-built agent personas, the Claude Code
skills used to build and tune that work, and the ZIL→MOO importer that produced
the Zork 1 bootstrap. The companion
[django-moo](https://gitlab.com/bubblehouse/django-moo) repository stays focused
on the MOO server itself.

## What's in this repo

| Path | What it is |
| ---- | ---------- |
| [`moo/agent/`](moo/agent/) | The `moo-agent` Python package — the CLI that connects to a MOO server and runs an LLM-driven persona. |
| [`moo/bootstrap/zork1/`](moo/bootstrap/zork1/) | Generated DjangoMOO bootstrap derived from the official Zork 1 source. Loaded into a server via `moo_init --bootstrap zork1`. |
| [`extras/agents/`](extras/agents/) | Pre-built agent personas (`gamer`, `mason`, `tinker`, `joiner`, `harbinger`, `cliff`, `newman`, …) and their shared `baseline.md` rules. Each is a directory you can pass to `moo-agent run`. |
| [`extras/skills/`](extras/skills/) | Claude Code skills used while building DjangoMOO and moo-agent — `verb-author`, `game-designer`, `tech-librarian`, `sandbox-auditor`, `agent-trainer`, `zork-shakedown`. See [extras/skills/README.md](extras/skills/README.md). |
| [`moo/zil_import/`](moo/zil_import/) | ZIL→DjangoMOO translator. Reads Infocom-style ZIL source and emits a `moo/bootstrap/<game>/` Python package. Game-agnostic; Zork 1 is the reference target. |

## Installation

```bash
pip install moo-agent
```

## Quick Start

```bash
# Initialize a new agent configuration directory
moo-agent init --name MyAgent \
    --host moo.example.com --port 8022 \
    --user myagent ./my-agent

# Run the agent
moo-agent run ./my-agent
```

## Documentation

Full documentation is available at [ReadTheDocs](https://moo-agent.readthedocs.io/).

## License

AGPL-3.0 — see [LICENSE](LICENSE).

### Zork 1

The optional `zork1` bootstrap (`moo/bootstrap/zork1/`) is a derivative work
of the Zork 1 source released under the MIT License by Microsoft / Activision
Publishing, Inc. in 2025. Its license and full attribution live in
`moo/bootstrap/zork1/LICENSE`; the rest of this project is AGPL-3.0.
Upstream source: <https://github.com/the-infocom-files/zork1>. Zork is a
registered trademark of Activision Publishing, Inc.; moo-agent is not
affiliated with, endorsed by, or sponsored by Microsoft or Activision.
