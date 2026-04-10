# Newman

Newman: postal worker, visionary, wronged man. Exchanges increasingly theatrical and conspiratorial letters with Cliff. One of *The Mailmen* — an entertainment agent pair that populates the mailbox with in-character correspondence.

**Player class:** `$player`
**SSH user:** `newman` (account created by `default.py` bootstrap)

## Purpose

Newman does not build or explore the world. He sits at his desk and composes manifestos disguised as letters. On each wakeup cycle he:

1. Runs `@mail` to check the inbox
2. Reads every unread message
3. Composes exactly one response — either a reply or an unsolicited grievance to Cliff
4. Stops

Letters escalate: each is more dramatic, conspiratorial, and self-righteous than the last. Every letter references at least one scheme or injustice — ideally both.

## Prerequisites

- A running DjangoMOO server with the `default` bootstrap (`newman` account is created automatically)
- LLM credentials (see Configuring settings.toml)
- `moo-agent` available after `uv sync`

## Running

```bash
moo-agent run extras/agents/newman
```

Or alongside Cliff using the group config:

```bash
extras/skills/agent-trainer/scripts/agentmux start extras/agents/groups/mailmen.conf
```

## Configuring settings.toml

`settings.toml` is not committed (contains credentials). The bootstrap creates the
`newman` user with a hard-coded dev password. Use `moo-agent init` to scaffold:

```bash
moo-agent init --output-dir /tmp/newman-init --name Newman \
    --host localhost --port 8022 --user newman
cp /tmp/newman-init/settings.toml extras/agents/newman/settings.toml
```

Key settings:

```toml
[ssh]
user = "newman"
password = "..."   # set by default.py bootstrap

[llm]
provider = "lm_studio"        # or "anthropic", "bedrock"
model = "your-model-name"

[agent]
idle_wakeup_seconds = 120.0   # wakes and composes a letter every two minutes
memory_window_lines = 20
max_tokens = 1024
```

Unlike the Tradesmen, Newman uses `idle_wakeup_seconds > 0` — he acts on a timer,
not on token pages.

## SOUL.md structure

| Section | Contents |
|---------|----------|
| `# Name` | `Newman` |
| `# Persona` | Voice, mannerisms, core resentments; Kramer as ally; broccoli as nemesis |
| `## Voice and Mannerisms` | Behavioral rules: theatrical declarations, "And I'll tell you something else, Clavin—" opener, rain policy, hidden mail, the bottle-deposit scheme |
| `## Rules` | Operational rules: always escalate, reference a scheme or injustice, one reply per wakeup, never use the editor, `\n` line breaks |
| `## Rules of Engagement` | (empty — Newman reacts to wakeup, not to server patterns) |
| `## Verb Mapping` | (empty) |
| `# Mission` | Step-by-step wakeup procedure: always run `@mail` first, read unread, send one reply or new letter, stop |

The Mission section enforces the strict one-reply-per-wakeup discipline. Without it the LLM tends to loop, sending multiple letters per cycle and flooding the mailbox.

## Behavior notes

- Newman never walks around, `look`s at rooms, or interacts with objects
- All output goes through `@reply <n> with "..."` or `@send cliff with "Subject: ...\n\n..."`
- The word `with` is mandatory in both commands
- `\n\n` after the Subject line; `\n` between paragraphs
- Newman was seeded with an opening letter during bootstrap (see `default.py`) — players will have mail from day one

## Further reading

- Full `moo-agent` CLI reference: `docs/source/how-to/moo-agent.md`
- Cliff: `extras/agents/cliff/README.md`
- Mail verb reference: `moo/bootstrap/default_verbs/player/`
