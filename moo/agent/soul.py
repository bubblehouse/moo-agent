"""
Soul loading and parsing for moo-agent.

Parses SOUL.md and SOUL.patch.md using the mistune AST renderer. The core soul
(SOUL.md) is immutable at runtime. The operational layer (SOUL.patch.md) is
append-only and agent-writable.

Does not import from moo.core or trigger Django setup.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import mistune


@dataclass
class Rule:
    pattern: str
    command: str


@dataclass
class VerbMapping:
    intent: str
    template: str


@dataclass
class Soul:
    name: str = ""
    mission: str = ""
    persona: str = ""
    context: str = ""
    rules: list[Rule] = field(default_factory=list)
    verb_mappings: list[VerbMapping] = field(default_factory=list)


# Matches both ASCII arrow (->) and unicode arrow (→)
_ARROW_RE = re.compile(r"\s*[-–]>\s*|→")

_SECTION_RULES = "rules of engagement"
_SECTION_VERBS = "verb mapping"
_SECTION_CONTEXT = "context"


def _extract_text(node) -> str:
    """Recursively extract plain text from a mistune AST node or list of nodes."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_extract_text(c) for c in node)
    if isinstance(node, dict):
        node_type = node.get("type", "")
        if node_type == "codespan":
            return node.get("raw", "")
        raw = node.get("raw", "")
        if raw:
            return raw
        children = node.get("children", [])
        return _extract_text(children)
    return ""


def _resolve_links(node, base_path: Path) -> str:
    """
    Recursively extract text from a node, replacing markdown links with the
    content of the linked file when the path resolves to an existing file.

    Non-file links fall back to the link's display text.
    """
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_resolve_links(c, base_path) for c in node)
    if isinstance(node, dict):
        node_type = node.get("type", "")
        if node_type == "link":
            url = node.get("attrs", {}).get("url", "")
            link_path = (base_path / url).resolve()
            if link_path.exists() and link_path.suffix in (".md", ".txt"):
                return link_path.read_text(encoding="utf-8")
            # Fallback: include the link's display text
            return _extract_text(node.get("children", []))
        if node_type == "codespan":
            return node.get("raw", "")
        raw = node.get("raw", "")
        if raw:
            return raw
        children = node.get("children", [])
        return _resolve_links(children, base_path)
    return ""


def _parse_md_file(path: Path) -> Soul:
    """Parse a single SOUL.md-format file into a Soul dataclass."""
    soul = Soul()
    text = path.read_text(encoding="utf-8")
    md = mistune.create_markdown(renderer="ast")
    tokens = md(text)

    current_h1 = None
    current_h2 = None
    body_lines: list[str] = []
    context_parts: list[str] = []

    def flush(h1, h2, lines):
        content = "\n".join(lines).strip()
        if not content:
            return
        if h1 == "name":
            soul.name = content
        elif h1 == "mission":
            soul.mission = content
        elif h1 == "persona":
            if h2 is None:
                soul.persona = content
        # Rules and verb mappings are handled per list_item, not flushed as body

    for token in tokens:
        tok_type = token.get("type", "")

        if tok_type == "heading":
            flush(current_h1, current_h2, body_lines)
            body_lines = []
            level = token.get("attrs", {}).get("level", 1)
            heading_text = _extract_text(token.get("children", [])).strip().lower()
            if level == 1:
                current_h1 = heading_text
                current_h2 = None
            elif level == 2:
                current_h2 = heading_text

        elif current_h2 == _SECTION_CONTEXT and tok_type in ("list", "paragraph", "block_text"):
            # Resolve any file links and accumulate context content
            for child in token.get("children", []):
                resolved = _resolve_links(child, path.parent)
                if resolved.strip():
                    context_parts.append(resolved.strip())

        elif tok_type == "list":
            # Walk list items for rules/verb mappings
            section = current_h2 or current_h1 or ""
            for item in token.get("children", []):
                raw = _extract_text(item.get("children", [])).strip()
                # Strip leading backticks if pattern is wrapped in code span
                raw = raw.strip("`")
                parts = _ARROW_RE.split(raw, maxsplit=1)
                if len(parts) == 2:
                    left, right = parts[0].strip(), parts[1].strip()
                    if section == _SECTION_RULES:
                        soul.rules.append(Rule(pattern=left, command=right))
                    elif section == _SECTION_VERBS:
                        soul.verb_mappings.append(VerbMapping(intent=left, template=right))

        elif tok_type == "paragraph":
            body_lines.append(_extract_text(token.get("children", [])).strip())

        elif tok_type == "block_text":
            body_lines.append(_extract_text(token.get("children", [])).strip())

    flush(current_h1, current_h2, body_lines)

    if context_parts:
        soul.context = "\n\n".join(context_parts)

    return soul


def parse_soul(config_dir: Path) -> Soul:
    """
    Load and merge SOUL.md and SOUL.patch.md from config_dir.

    Base entries (SOUL.md) are listed first; patch entries follow. When rules are
    checked in order, base rules take precedence over patch rules.

    If a baseline.md exists in config_dir's parent directory, its text is
    prepended to soul.context before any SOUL.md context is appended.
    """
    base = _parse_md_file(config_dir / "SOUL.md")

    baseline_path = config_dir.parent / "baseline.md"
    if baseline_path.exists():
        baseline_text = baseline_path.read_text(encoding="utf-8")
        if base.context:
            base.context = baseline_text + "\n\n" + base.context
        else:
            base.context = baseline_text

    patch_path = config_dir / "SOUL.patch.md"
    if patch_path.exists() and patch_path.stat().st_size > 0:
        patch = _parse_md_file(patch_path)
        base.rules.extend(patch.rules)
        base.verb_mappings.extend(patch.verb_mappings)

    return base


def compile_rules(soul: Soul) -> list[tuple[re.Pattern, str]]:
    """Pre-compile rule patterns for O(1) matching at runtime."""
    return [(re.compile(r.pattern), r.command) for r in soul.rules]


def append_patch(config_dir: Path, entry_type: str, pattern_or_intent: str, command: str) -> None:
    """
    Append a single new entry to SOUL.patch.md.

    entry_type is "rule" or "verb". Skips the write if an identical entry already
    exists. Creates the section header if this is the first entry of that type.
    """
    patch_path = config_dir / "SOUL.patch.md"
    new_line = f"- {pattern_or_intent} -> {command}"

    existing = patch_path.read_text(encoding="utf-8") if patch_path.exists() else ""

    # Deduplication
    if new_line in existing:
        return

    section_header = "## Rules of Engagement" if entry_type == "rule" else "## Verb Mapping"

    lines_to_append: list[str] = []
    if section_header not in existing:
        if existing and not existing.endswith("\n"):
            lines_to_append.append("\n")
        lines_to_append.append(f"\n{section_header}\n")

    lines_to_append.append(f"{new_line}\n")

    with open(patch_path, "a", encoding="utf-8") as f:
        f.write("".join(lines_to_append))
