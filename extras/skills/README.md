# Claude Code Skills

Custom Claude Code skills used while building DjangoMOO and moo-agent. Each skill is a self-contained directory with a `SKILL.md` (the AI agent prompt) and a `references/` folder with supporting documentation.

## Skills

| Skill | What it does |
| ----- | ------------ |
| [verb-author](verb-author/README.md) | Write and review DjangoMOO verb files, including `#!moo` shebang syntax, RestrictedPython execution, the moo.sdk API, and verb testing. |
| [game-designer](game-designer/README.md) | Design and build themed multi-room environments via SSH wizard commands. |
| [tech-librarian](tech-librarian/README.md) | Sync documentation across the layers in django-moo — Sphinx guides, AI skill files, and AGENTS.md. |
| [sandbox-auditor](sandbox-auditor/README.md) | Conduct security audits of the RestrictedPython verb sandbox. |
| [agent-trainer](agent-trainer/README.md) | Iteratively tune a running moo-agent by reading session logs and updating SOUL.md / baseline.md / brain.py. |
| [zork-shakedown](zork-shakedown/README.md) | End-to-end ZIL→DjangoMOO debugging — drive `zork1.local` through MooSSH to find translator/server bugs, or close translation gaps inside `extras/zil_import/`. |

## How skills are loaded

Claude Code loads skills from `~/.claude/skills/` and from project-level `.claude/skills/` directories. The skills here are symlinked into `moo-agent/.claude/skills/` so they are available in any Claude Code session opened in this repository:

```
.claude/skills/verb-author       -> ../../extras/skills/verb-author
.claude/skills/game-designer     -> ../../extras/skills/game-designer
.claude/skills/tech-librarian    -> ../../extras/skills/tech-librarian
.claude/skills/sandbox-auditor   -> ../../extras/skills/sandbox-auditor
.claude/skills/agent-trainer     -> ../../extras/skills/agent-trainer
.claude/skills/zork-shakedown    -> ../../extras/skills/zork-shakedown
```

The symlinks live in `.claude/skills/` at the project root (not in `~/.claude/`). Claude Code discovers them as project-scoped skills.

To add a new skill, create a directory here with a `SKILL.md`, then symlink it:

```bash
ln -s ../../extras/skills/my-skill .claude/skills/my-skill
```

## Skill file structure

```
skill-name/
  SKILL.md          # AI agent instructions — the skill "prompt"
  README.md         # Human-readable docs (this kind of file)
  references/       # Supporting reference documents read by the agent
  assets/           # Templates, examples (optional)
  tools/            # Python scripts invoked by the skill (optional)
  environments/     # Build artifacts, e.g. YAML for game-designer (optional)
  snippets/         # Copy-paste patterns (optional)
```

`SKILL.md` must have a YAML frontmatter block with at minimum `name` and `description`:

```yaml
---
name: my-skill
description: One-line description used by Claude to decide when to invoke this skill.
---
```

The `description` field is what Claude Code matches against when deciding whether to auto-invoke a skill. Make it specific to the task domain.
