# tech-librarian

A Claude Code skill for keeping documentation in sync across the three layers in django-moo.

## When to use it

Invoke this skill when:

- New features have landed and need to be documented
- A bug fix corrected an API assumption that lives in docs or skill files
- You want to audit documentation drift across layers
- You're doing a general "doc pass" after a batch of changes

Trigger phrases: "do a doc pass", "audit documentation drift", "update Sphinx to match recent changes", "sync the docs", "keep the layers consistent".

## How to invoke

```
/tech-librarian
/tech-librarian sync docs after recent verb changes
```

## The three documentation layers

Every significant fact about the system should appear in all three layers that cover it:

| Layer | Audience | Location |
|-------|----------|----------|
| Sphinx guides | Human developers reading docs | `docs/source/` |
| AI skill files | Claude Code agents doing tasks | `extras/skills/*/SKILL.md` and `references/` |
| `AGENTS.md` | Any AI agent running in the repo | `AGENTS.md` (root) |

Skills and `AGENTS.md` tend to be ahead of Sphinx — corrections and gotchas land there first. The librarian finds those gaps and closes them.

## What it does

The skill follows a 4-phase workflow:

1. **Orient** — reads recent git history to identify what changed since the last sync pass; checks project memory for undocumented gotchas
2. **Gap detection** — works through a checklist of common drift types (output mechanisms, API names, return value behavior, parser behavior, SDK functions, sandbox restrictions)
3. **Port** — writes the missing content into whichever layer(s) need it, with one commit per destination
4. **Verify** — spot-checks corrected facts across layers; validates the Sphinx build with `sphinx-build -b dummy` and `sphinx-lint`

## Reference files

| File | Contents |
|------|----------|
| `references/layers.md` | Canonical file list for each layer, scope boundaries, and how to read each |
| `references/translation.md` | Audience translation rules — how to rewrite skill content for Sphinx and vice versa |

## README files are also in scope

The `extras/skills/*/README.md` files are user-facing documentation for each skill. When skill capabilities change (new reference files, new trigger phrases, new workflow phases), update the relevant README as part of the sync pass.
