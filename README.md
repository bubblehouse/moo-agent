# moo-agent

Autonomous AI agent client for
[DjangoMOO](https://gitlab.com/bubblehouse/django-moo) servers.

`moo-agent` connects to a running MOO server via SSH and drives an AI persona using an
LLM backend (Anthropic, AWS Bedrock, or a local LM Studio model). The agent reads its
personality and operational rules from a `SOUL.md` file and can learn new rules at
runtime via `SOUL.patch.md`.

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

AGPL — see [LICENSE](LICENSE).
