"""
Pure parser for the LLM response directive grammar used by Brain._llm_cycle.

This module owns the regex constants and the line-by-line parser that turns a
raw LLM response body into an ordered list of Directives plus any leftover
"thought" lines. It has no side effects — Brain walks the returned list and
dispatches each directive in source order.

The directive grammar is documented in brain._PATCH_INSTRUCTIONS. Summary:

  GOAL:            <one-line objective>
  PLAN:            <pipe-separated remaining plan>
  SOUL_PATCH_RULE: <pattern> -> <command>
  SOUL_PATCH_VERB: <intent>  -> <template>
  SOUL_PATCH_NOTE: <free-form note>
  BUILD_PLAN:      <first yaml line>   # continues on the following lines
                    <more yaml>         # until the next top-level directive
  SCRIPT:          <step1> | <step2>
  COMMAND:         <single MOO command>
  DONE:            <one-line summary>

Line pre-processing:
  - Markdown bold wrappers around the keyword are stripped
    ("**COMMAND:** foo" -> "COMMAND: foo").
  - XML action/tool wrappers are unwrapped ("<action>foo</action>" -> "foo").

Parser quirks preserved from the original in-Brain implementation:
  - "COMMAND: SCRIPT: a | b" — the nested SCRIPT: is promoted to a script
    directive. Required because some models emit a COMMAND wrapper around a
    script body.
  - BUILD_PLAN: accumulates following lines until the next top-level
    directive, flushing on the next directive or end of response.
  - Backticks around a COMMAND: payload are stripped.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

_PATCH_RULE_RE = re.compile(r"^SOUL_PATCH_RULE:\s*(.+)$")
_PATCH_VERB_RE = re.compile(r"^SOUL_PATCH_VERB:\s*(.+)$")
_PATCH_NOTE_RE = re.compile(r"^SOUL_PATCH_NOTE:\s*(.+)$")
_BUILD_PLAN_RE = re.compile(r"^BUILD_PLAN:\s*(.+)$")
_COMMAND_RE = re.compile(r"^COMMAND:\s*(.+)$")
_SCRIPT_RE = re.compile(r"^SCRIPT:\s*(.+)$")
_DONE_RE = re.compile(r"^DONE:\s*(.+)$")
_GOAL_RE = re.compile(r"^GOAL:\s*(.+)$")
_PLAN_RE = re.compile(r"^PLAN:\s*(.+)$")

_MD_BOLD_RE = re.compile(r"^\*+\s*([A-Z_]+:)\s*\*+\s*")
_XML_WRAPPER_RE = re.compile(r"^<\w+>(.*)</\w+>$")

_ROOM_NAME_RE = re.compile(r"^  - name:\s*[\"']?([^\"'\n]+)[\"']?", re.MULTILINE)


DirectiveKind = Literal[
    "goal",
    "plan",
    "patch_rule",
    "patch_verb",
    "patch_note",
    "build_plan",
    "script",
    "done",
    "command",
]


@dataclass
class Directive:
    kind: DirectiveKind
    value: str  # directive-specific payload (see per-kind notes below)


@dataclass
class ParsedResponse:
    """
    Result of parse_llm_response.

    - directives: ordered list of Directive — Brain walks this and dispatches
      each in source order. Per-kind payload:

        goal        stripped goal text
        plan        raw payload (pipe-separated; split by the consumer)
        patch_rule  raw directive (passed to append_patch_directive)
        patch_verb  raw directive (passed to append_patch_directive)
        patch_note  raw directive (passed to append_patch_directive)
        build_plan  accumulated BUILD_PLAN body (newline-joined)
        script      the full "SCRIPT: ..." line, ready for _handle_script_line
        done        stripped summary text
        command     stripped MOO command (backticks stripped)

    - thought_lines: lines that did not match any directive. The consumer
      appends them to the rolling window as thoughts.
    """

    directives: list[Directive] = field(default_factory=list)
    thought_lines: list[str] = field(default_factory=list)


def parse_llm_response(text: str) -> ParsedResponse:
    """
    Parse an LLM response body into ordered directives + leftover thought lines.

    Pure function: no I/O, no Brain state, no side effects.
    """
    result = ParsedResponse()
    in_build_plan = False
    build_plan_lines: list[str] = []

    def flush_build_plan() -> None:
        nonlocal in_build_plan, build_plan_lines
        if in_build_plan and build_plan_lines:
            result.directives.append(Directive("build_plan", "\n".join(build_plan_lines)))
        in_build_plan = False
        build_plan_lines = []

    for raw_line in text.splitlines():
        line = _MD_BOLD_RE.sub(r"\1 ", raw_line)
        line = _XML_WRAPPER_RE.sub(r"\1", line.strip())

        patch_rule = _PATCH_RULE_RE.match(line)
        patch_verb = _PATCH_VERB_RE.match(line)
        patch_note = _PATCH_NOTE_RE.match(line)
        build_plan = _BUILD_PLAN_RE.match(line)
        cmd_match = _COMMAND_RE.match(line)
        script_match = _SCRIPT_RE.match(line)
        done_match = _DONE_RE.match(line)
        goal_match = _GOAL_RE.match(line)
        plan_match = _PLAN_RE.match(line)

        is_directive = any(
            [
                goal_match,
                plan_match,
                patch_rule,
                patch_verb,
                patch_note,
                build_plan,
                cmd_match,
                script_match,
                done_match,
            ]
        )
        if in_build_plan and is_directive:
            flush_build_plan()

        if in_build_plan:
            build_plan_lines.append(line)
            continue

        if goal_match:
            result.directives.append(Directive("goal", goal_match.group(1).strip()))
        elif plan_match:
            result.directives.append(Directive("plan", plan_match.group(1)))
        elif patch_rule:
            result.directives.append(Directive("patch_rule", patch_rule.group(1)))
        elif patch_verb:
            result.directives.append(Directive("patch_verb", patch_verb.group(1)))
        elif patch_note:
            result.directives.append(Directive("patch_note", patch_note.group(1)))
        elif build_plan:
            first_line = build_plan.group(1).strip()
            build_plan_lines = [first_line] if first_line else []
            in_build_plan = True
        elif script_match:
            result.directives.append(Directive("script", line))
        elif done_match:
            result.directives.append(Directive("done", done_match.group(1).strip()))
        elif cmd_match:
            command_text = cmd_match.group(1).strip().strip("`")
            # Nested "COMMAND: SCRIPT: a | b" — promote to a script directive
            # so _handle_script_line runs instead of sending the literal
            # "SCRIPT: ..." string to the MOO server. Also emit an empty
            # command directive so any earlier COMMAND: in the same response
            # is overwritten — matches the original in-loop semantics where
            # `command_line = ""` was reassigned after the nested script ran.
            if _SCRIPT_RE.match(command_text):
                result.directives.append(Directive("script", command_text))
                result.directives.append(Directive("command", ""))
            else:
                result.directives.append(Directive("command", command_text))
        else:
            result.thought_lines.append(line)

    flush_build_plan()
    return result


def extract_room_names_from_yaml(text: str) -> list[str]:
    """Extract top-level room names (2-space indent) from a build plan YAML string."""
    return _ROOM_NAME_RE.findall(text)
