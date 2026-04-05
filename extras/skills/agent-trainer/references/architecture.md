# Agent Architecture Reference

## Directory layout

```
extras/agents/
├── baseline.md    # Shared context prepended to every agent's SOUL
├── mason/         # $player — rooms, exits, descriptions
├── tinker/        # $programmer — $thing objects and verbs (incl. secret exits)
├── joiner/        # $player — $furniture and $container objects
└── harbinger/     # $programmer — NPCs in ~10% of rooms (random roll)

Each agent directory:
    ├── SOUL.md         # Persona, mission, rules, verb mappings — agent-specific
    ├── SOUL.patch.md   # Agent-writable: runtime-learned rules (append-only)
    ├── settings.toml   # SSH credentials, LLM provider, rate/token settings
    └── logs/
        └── 2026-04-02T20-51-56.log   # One log per session, named by start time

mason/ also has:
    └── builds/         # BUILD_PLAN: YAML files saved at session start

moo/agent/
├── brain.py       # Perception-action loop, LLM calls, error detection
├── cli.py         # Entry point: connects SSH, creates brain, manages log file
├── connection.py  # asyncssh session, PREFIX/SUFFIX delimiter extraction
├── soul.py        # SOUL.md parser: produces Soul dataclass
└── tui.py         # Optional terminal UI (skipped when stdin is not a TTY)
```

## SOUL.md format

Parsed by `soul.py`. The top-level structure:

```markdown
# Name
<agent name>

# Mission
<objective paragraph — included verbatim in system prompt>

# Persona
<persona description — included verbatim>

## Rules of Engagement
- `<pattern>` -> <command>     (compiled to regex; matched against server output)

## Verb Mapping
- <intent> -> <moo command>    (intent names the LLM can use as shortcuts)

## Context
- [linked file](../path/to/file.md)    (content substituted inline)
- Plain text paragraphs also work

## Response Format
<format instructions — included verbatim>
```

**Unknown `## Subsections` under `# Persona`** are folded into `soul.context` and sent to the LLM as additional context. This means you can add any new `##` section under `# Persona` and it will automatically reach the model without any code changes.

## baseline.md

A plain Markdown file injected into `soul.context` before any content from `SOUL.md`. Intended for facts that apply to every agent: MOO command syntax, sandbox restrictions, gotchas, object model rules.

Structure is free-form `##` sections. Anything under a `##` heading is included.

The build example at the bottom of `baseline.md` is the most important single piece of guidance — the agent refers to it as a template for multi-step build sequences.

## brain.py key internals

### `_ERROR_PREFIXES`

Tuple of strings. Each server output line is tested with `first_line.startswith(prefix)`. If any match, the current SCRIPT queue is cleared and control returns to the LLM.

```python
_ERROR_PREFIXES = (
    "Error:",
    "Traceback",
    "There is no ",
    "Huh?",
    ...
)
```

The game's default "unrecognized command" response is `"Huh? I don't understand that command."` from the `huh2` verb on `$room`, delivered via `player.tell()`. This arrives wrapped in OUTPUTPREFIX/OUTPUTSUFFIX and is visible to the agent.

### Script queue

When the LLM emits `SCRIPT: cmd1 | cmd2 | cmd3`, the brain queues all commands. It sends one command, waits for the server response (0.3s quiet period), then sends the next. If any response matches `_ERROR_PREFIXES`, the queue is cleared and the LLM is called for a new cycle.

Silent commands (no server output) advance the queue after the 0.3s timeout — they don't stall the loop.

### LLM error handling

- `529 Overloaded`: retried 3× with exponential backoff (5s, 10s, 20s)
- `400` and all other errors: logged as `[LLM error]`, cycle aborted, status set to READY
- The 60-second wakeup loop fires a new LLM cycle automatically — so a stuck agent will retry every 60 seconds

### Wakeup loop

Fires `_llm_cycle()` every 60 seconds if no server output has arrived. Prevents the agent from waiting forever when the server sends nothing (e.g. after a silent command, or after an LLM error).

## Output mechanisms

| Mechanism | Timing | Path |
|-----------|--------|------|
| `print(msg)` in verb | After Celery task completes | Wrapped in OUTPUTPREFIX/OUTPUTSUFFIX |
| `player.tell(msg)` | Immediate (Kombu message) | Wrapped in OUTPUTPREFIX/OUTPUTSUFFIX |
| `write(obj, msg)` | Immediate, low-level | Wrapped in OUTPUTPREFIX/OUTPUTSUFFIX |

All three arrive at the agent wrapped in the session's OUTPUTPREFIX/OUTPUTSUFFIX markers and are extracted by `connection.py`'s `_extract_delimited()`. The log tag is always `[server]` (or `[server_error]` if it matches `_ERROR_PREFIXES`).

The Celery task return value `[]` means no `print()` output was produced. It does not mean no output was sent — `tell()` output travels via Kombu and is independent of the Celery return value.

## Log format

Each line: `[HH:MM:SS] [kind] text`

| Kind | Meaning |
|------|---------|
| `[system]` | Connection events, session start/resume |
| `[goal]` | LLM emitted a `GOAL:` line |
| `[thought]` | LLM emitted a `DONE:` line, or internal brain note |
| `[action]` | Command sent to the MOO server |
| `[server]` | Server response (normal) |
| `[server_error]` | Server response that matched `_ERROR_PREFIXES` |
| `[operator]` | Text typed by a human in the TUI |

`[server_error]` entries are the primary signal that error detection is working. If a known-bad server response appears as `[server]` instead of `[server_error]`, add its prefix to `_ERROR_PREFIXES`.
