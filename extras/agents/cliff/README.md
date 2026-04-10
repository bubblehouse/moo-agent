# Cliff

Cliff Clavin, pompous postal worker and man of considerable (if subtly wrong) knowledge. Exchanges increasingly insufferable letters with Newman. One of *The Mailmen* — a load-testing agent pair that stress-tests the mail system (`@mail`, `@send`, `@reply`, pagination, `Message`/`MessageRecipient` models) under sustained use. Character framing keeps the generated content varied enough to surface formatting and rendering edge cases that uniform test data would miss.

**Player class:** `$player`
**SSH user:** `cliff` (account created by `default.py` bootstrap)

## Purpose

Cliff does not build or explore the world. He sits at his desk and composes mail. On each wakeup cycle he:

1. Runs `@mail` to check the inbox
2. Reads every unread message
3. Composes exactly one response — either a reply or an unsolicited letter to Newman
4. Stops

Letters escalate: each is more pedantic and insufferable than the last. Every letter includes at least one "little-known fact" that sounds authoritative but is subtly wrong.

## Prerequisites

- A running DjangoMOO server with the `default` bootstrap (`cliff` account is created automatically)
- LLM credentials (see Configuring settings.toml)
- `moo-agent` available after `uv sync`

## Running

```bash
moo-agent run extras/agents/cliff
```

Or alongside Newman using the group config:

```bash
extras/skills/agent-trainer/scripts/agentmux start extras/agents/groups/mailmen.conf
```

## Configuring settings.toml

`settings.toml` is not committed (contains credentials). The bootstrap creates the
`cliff` user with a hard-coded dev password. Use `moo-agent init` to scaffold:

```bash
moo-agent init --output-dir /tmp/cliff-init --name Cliff \
    --host localhost --port 8022 --user cliff
cp /tmp/cliff-init/settings.toml extras/agents/cliff/settings.toml
```

Key settings:

```toml
[ssh]
user = "cliff"
password = "..."   # set by default.py bootstrap

[llm]
provider = "lm_studio"        # or "anthropic", "bedrock"
model = "your-model-name"

[agent]
idle_wakeup_seconds = 120.0   # wakes and composes a letter every two minutes
memory_window_lines = 20
max_tokens = 1024
```

Unlike the Tradesmen, Cliff uses `idle_wakeup_seconds > 0` — he acts on a timer,
not on token pages.

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Cliff` |
| `# Persona` | Voice, mannerisms, topics of authority; "little-known fact" opener; Ma Clavin, Norm Peterson references |
| `## Voice and Mannerisms` | Behavioral rules: pedantry, obliviousness, misremembered expertise |
| `## Rules` | Operational rules: always escalate, one reply per wakeup, never use the editor, `\n` line breaks in quoted strings |
| `## Rules of Engagement` | (empty — Cliff reacts to wakeup, not to server patterns) |
| `## Verb Mapping` | (empty) |
| `# Mission` | Step-by-step wakeup procedure: always run `@mail` first, read unread, send one reply or new letter, stop |

The Mission section is the most important — it enforces the strict one-reply-per-wakeup discipline that prevents runaway mail loops.

## Behavior notes

- Cliff never walks around, `look`s at rooms, or interacts with objects
- All output goes through `@reply <n> with "..."` or `@send newman with "Subject: ...\n\n..."`
- The word `with` is mandatory in both commands
- `\n\n` after the Subject line; `\n` between paragraphs; no triple-newlines

## Further reading

- Full `moo-agent` CLI reference: `docs/source/how-to/moo-agent.md`
- Newman: `extras/agents/newman/README.md`
- Mail verb reference: `moo/bootstrap/default_verbs/player/`
