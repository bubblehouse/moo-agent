# Contributing to moo-agent

Thank you for your interest in contributing to moo-agent! This guide covers everything you need to go from zero to a merged contribution.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Code Style](#code-style)
- [Testing](#testing)
- [Commit Messages](#commit-messages)
- [Merge Request Process](#merge-request-process)
- [Adding Dependencies](#adding-dependencies)
- [Documentation](#documentation)
- [Getting Help](#getting-help)

---

## Code of Conduct

This project follows a simple principle: be respectful, constructive, and collaborative. Harassment, discrimination, or bad-faith behaviour will not be tolerated. If you experience a problem, contact the maintainer at <phil@bubblehouse.org>.

---

## Ways to Contribute

- **Bug reports** — open an issue describing what went wrong
- **Feature requests** — open an issue describing what you'd like and why
- **Code** — fix a bug, implement a feature, improve performance
- **Tests** — increase coverage or add missing test cases
- **Documentation** — improve the user guide, API docs, or this file
- **LLM backends** — contribute support for additional inference providers

---

## Reporting Bugs

Before opening an issue, search existing issues to avoid duplicates.

When filing a bug, include:

1. moo-agent version (from `pyproject.toml` or `pip show moo-agent`)
2. Python version (`python --version`)
3. LLM backend in use (Anthropic, Bedrock, LM Studio)
4. Steps to reproduce the problem
5. What you expected to happen
6. What actually happened (paste the full traceback or session log excerpt)
7. Relevant configuration (redact any API keys or credentials)

---

## Suggesting Features

Open an issue with the `enhancement` label. Describe:

- The problem you're trying to solve
- Your proposed solution
- Any alternatives you considered

Discuss significant changes before writing code so you don't spend time on something that won't fit the project's direction.

---

## Development Setup

### Prerequisites

- Python 3.11 (the project pins `>=3.11,<3.12`)
- [uv](https://docs.astral.sh/uv/) — Python package and project manager
- A running DjangoMOO server (see [django-moo](https://gitlab.com/bubblehouse/django-moo))
- `pre-commit`

### First-time setup

```bash
git clone https://gitlab.com/bubblehouse/moo-agent
cd moo-agent

# Install dependencies
uv sync

# Install pre-commit hooks
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

### Initialize a test agent

```bash
moo-agent init --name TestAgent \
    --host localhost --port 8022 \
    --user testagent ./test-agent

moo-agent run ./test-agent
```

---

## Project Structure

```
moo/agent/
  brain/          LLM reasoning loop and tool dispatch
  cli.py          Entry point: `moo-agent` command
  config.py       Agent configuration loading
  connection.py   AsyncSSH connection management
  llm_client.py   LLM provider abstraction (Anthropic, Bedrock, LM Studio)
  session_log.py  Structured session logging
  soul.py         SOUL.md / SOUL.patch.md loading and rule application
  tools.py        MOO-side tool implementations
  tui.py          Terminal UI (Rich)
  templates/      Default SOUL.md and config templates
  tests/          Test suite
docs/             Sphinx source for the user guide and API reference
```

Key files:

| File | Purpose |
|------|---------|
| `moo/agent/brain/` | Core reasoning loop |
| `moo/agent/llm_client.py` | Provider-agnostic LLM interface |
| `moo/agent/soul.py` | Personality and runtime rule loading |
| `moo/agent/connection.py` | SSH session and command I/O |
| `pyproject.toml` | Dependency management and tool configuration |

---

## Code Style

### Formatter

The project uses [Ruff](https://docs.astral.sh/ruff/formatter/) with a line length of 120 characters.

```bash
uv run ruff format moo
```

### Linter

[Pylint](https://pylint.readthedocs.io/) is used for static analysis. The minimum acceptable score is **8.0 / 10**.

```bash
uv run pylint moo
```

### General conventions

- Follow [PEP 8](https://peps.python.org/pep-0008/) except where Ruff overrides it.
- **Variables and functions:** `snake_case`
- **Classes:** `PascalCase`
- **Constants:** `SCREAMING_SNAKE_CASE`
- **File names:** `snake_case`
- Write type hints in new code.
- Comments and docstrings are complete sentences ending with a period.
- Imports are ordered: stdlib, then third-party, then local — Ruff handles formatting automatically.

---

## Testing

### Running the test suite

```bash
# All tests, in parallel, with coverage
uv run pytest -n auto --cov

# A single file
uv run pytest moo/agent/tests/test_soul.py

# View coverage after the run
uv run coverage report
```

### What to test

Every bug fix and new feature must include corresponding tests. Coverage must not decrease with your change.

### Writing tests

Tests live in `moo/agent/tests/`. Use `pytest` fixtures for shared setup. Integration tests that require a live MOO server should be marked `@pytest.mark.integration` and are skipped in CI unless a server is available.

---

## Commit Messages

moo-agent uses the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification, enforced by `commitlint` via the pre-commit `commit-msg` hook.

### Format

```
<type>(<scope>): <subject>

<body>
```

- **Subject:** lowercase, imperative mood, no trailing period, 50 characters max.
- **Body:** optional; explain *what* and *why*, not *how*; wrap at 72 characters.

### Types

| Type | When to use |
|------|-------------|
| `feat` | A new feature visible to users or agent authors |
| `fix` | A bug fix |
| `docs` | Documentation only |
| `style` | Formatting, whitespace — no logic change |
| `refactor` | Code change that is neither a fix nor a feature |
| `test` | Adding or fixing tests |
| `chore` | Build process, dependency updates, tooling |
| `ci` | CI/CD pipeline changes |

### Scopes

Use the component affected: `brain`, `soul`, `connection`, `llm`, `cli`, `tui`, `docs`, `ci`.

### Examples

```
feat(brain): add retry logic for failed LLM calls
fix(connection): handle SSH disconnect during tool execution
docs(readme): update quick-start instructions
test(soul): add coverage for SOUL.patch.md merging
chore(deps): upgrade anthropic to 0.51
```

Breaking changes must include a `BREAKING CHANGE:` footer:

```
feat(llm)!: remove OpenAI provider support

BREAKING CHANGE: Use LM Studio with an OpenAI-compatible endpoint instead.
```

---

## Merge Request Process

1. **Branch** off `main`:

   ```bash
   git checkout -b feat/my-feature
   ```

2. **Make your changes** following the style and testing guidelines above.

3. **Run checks locally** before pushing:

   ```bash
   uv run pytest -n auto --cov
   uv run pylint moo
   ```

4. **Push** and open a Merge Request targeting `main` on GitLab.

5. **Describe your MR:**
   - What changed and why
   - Whether there are breaking changes
   - Link to any related issues

6. **CI must pass.** The pipeline runs lint and tests automatically on every MR. A Pylint score below 8.0 or any failing test blocks the merge.

7. **Address review feedback** with additional commits (no force-pushing during review).

8. After merge, semantic-release automatically determines the next version from the commit history and publishes to PyPI.

---

## Adding Dependencies

Runtime dependencies:

```bash
uv add <package>
```

Development-only dependencies:

```bash
uv add --group dev <package>
```

`uv.lock` is updated automatically. Include a brief note in your MR description explaining why the new dependency is needed.

---

## Documentation

- **API docs** are generated by Sphinx from docstrings and published automatically to ReadTheDocs on every merge to `main`.
- **User guide** lives in `docs/source/` as Markdown files.
- Update `docs/` for any user-facing change.
- Keep `README.md` current with quick-start instructions.

---

## Getting Help

- **Issues:** <https://gitlab.com/bubblehouse/moo-agent/-/issues>
- **Documentation:** <https://moo-agent.readthedocs.io/>
- **Email:** <phil@bubblehouse.org>
