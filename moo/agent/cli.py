"""
CLI entrypoint for moo-agent.

Subcommands:
  moo-agent init  — create a new agent configuration directory
  moo-agent run   — connect to a MOO server and start the agent loop

Does not import from moo.core or trigger Django setup.
"""

import argparse
import asyncio
import datetime
import importlib.resources
import re
import sys
from pathlib import Path

from moo.agent.brain import Brain, looks_like_error
from moo.agent.config import load_config_dir
from moo.agent.connection import MooConnection
from moo.agent.soul import parse_soul
from moo.agent.tools import BUILDER_TOOLS_BY_NAME
from moo.agent.tui import LogEntry, MooTUI

_LOG_LINE_RE = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\] \[(\w+)\] (.*)")

# Kinds that are meaningful for session resumption; skip system/patch noise
_RESUME_KINDS = {"action", "server", "goal", "thought", "server_error"}
# How many recent entries to include in the prior-session summary
_RESUME_LINES = 40


def _read_prior_session(logs_dir: Path, current_log: Path) -> tuple[str, str]:
    """
    Find the most recent previous log file and extract session context.

    Returns (summary_text, last_goal). Both are empty strings if no prior log exists.
    The summary is injected into the brain's memory window so the agent knows
    where it left off without replaying the full history.
    """
    # Logs are named YYYY-MM-DDTHH-MM-SS.log, so lexicographic order equals chronological.
    prior_logs = sorted(p for p in logs_dir.glob("*.log") if p != current_log)
    if not prior_logs:
        return "", ""

    prev_log = prior_logs[-1]
    raw_lines = prev_log.read_text(encoding="utf-8").splitlines()

    # Parse into (kind, text) tuples, merging continuation lines
    entries: list[tuple[str, str]] = []
    cur_kind: str = ""
    cur_text: str = ""
    in_entry: bool = False
    for line in raw_lines:
        m = _LOG_LINE_RE.match(line)
        if m:
            if in_entry:
                entries.append((cur_kind, cur_text))
            _, cur_kind, cur_text = m.groups()
            in_entry = True
        elif in_entry:
            cur_text = cur_text + "\n" + line
    if in_entry:
        entries.append((cur_kind, cur_text))

    # Last recorded goal
    last_goal = ""
    for kind, text in reversed(entries):
        if kind == "goal":
            last_goal = text.removeprefix("[Goal] ").strip()
            break

    # If the prior session ended with a plan-exhaustion signal, override the
    # summary so the new session starts knowing all rooms are built.
    _PLAN_DONE_MARKER = "[Plan] All planned rooms built."
    if any(kind == "thought" and _PLAN_DONE_MARKER in text for kind, text in entries):
        return "All planned rooms are built. Do not emit BUILD_PLAN or dig rooms. Emit DONE: now.", last_goal

    # Recent relevant entries for the summary
    relevant = [(k, t) for k, t in entries if k in _RESUME_KINDS]
    recent = relevant[-_RESUME_LINES:]

    session_label = prev_log.stem  # e.g. "2026-03-28T23-33-51"
    summary_lines = [f"[Prior session: {session_label}]"]
    for kind, text in recent:
        first_line = text.split("\n")[0]
        if len(first_line) > 120:
            first_line = first_line[:117] + "..."
        summary_lines.append(f"  [{kind}] {first_line}")
    return "\n".join(summary_lines), last_goal


def cmd_init(args) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    template_pkg = importlib.resources.files("moo.agent.templates")

    files_to_write = {
        "SOUL.md": {
            "{agent_name}": args.name,
        },
        "SOUL.patch.md": {},
        "settings.toml": {
            "{host}": args.host,
            "{port}": str(args.port),
            "{user}": args.user,
        },
    }

    for filename, substitutions in files_to_write.items():
        dest = output_dir / filename
        if dest.exists() and not args.force:
            print(f"  skip  {dest}  (already exists; use --force to overwrite)")
            continue
        content = template_pkg.joinpath(filename).read_text(encoding="utf-8")
        for token, value in substitutions.items():
            content = content.replace(token, value)
        dest.write_text(content, encoding="utf-8")
        print(f"  wrote {dest}")

    print(f"\nConfig written to {output_dir}")
    print(f"Edit {output_dir / 'SOUL.md'} to define the agent's mission and persona.")
    print(f"Set the {args.api_key_env!r} environment variable before running.")
    print(f"\nTo start the agent:\n  moo-agent run {output_dir}")


async def run_agent(config, soul, config_dir: Path, startup_delay: float = 0.0) -> None:
    logs_dir = config_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    session_ts = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_path = logs_dir / f"{session_ts}.log"
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: WPS515

    prior_summary, prior_goal = _read_prior_session(logs_dir, log_path)

    conn = MooConnection(config.ssh)
    tui: MooTUI | None = None

    def _add(kind, text):
        if kind == "thought" and text.startswith("[Goal]"):
            kind = "goal"
        elif kind == "server" and looks_like_error(text):
            kind = "server_error"
        entry = LogEntry(kind=kind, text=text)
        if tui is not None:
            tui.add_entry(entry)
        log_file.write(f"[{entry.timestamp}] [{kind}] {text}\n")
        log_file.flush()

    def _send_and_log(cmd: str) -> None:
        conn.send(cmd)
        _add("action", cmd)

    # Merge tool names from soul (SOUL.md ## Tools) and config (settings.toml),
    # preserving order and deduplicating. Soul takes priority so the agent's
    # persona file is the canonical declaration of its capabilities.
    seen: set[str] = set()
    tool_names: list[str] = []
    for name in soul.tools + config.agent.tools:
        if name not in seen:
            seen.add(name)
            tool_names.append(name)
    tools = [BUILDER_TOOLS_BY_NAME[name] for name in tool_names if name in BUILDER_TOOLS_BY_NAME]
    unknown = [n for n in tool_names if n not in BUILDER_TOOLS_BY_NAME]
    if unknown:
        _add("thought", f"[Config] Unknown tool names ignored: {unknown}")

    brain = Brain(
        soul=soul,
        config=config,
        send_command=_send_and_log,
        on_thought=lambda t: _add("thought", t),
        config_dir=config_dir,
        on_status_change=lambda s: tui.set_status(s) if tui is not None else None,
        prior_session_summary=prior_summary,
        prior_goal=prior_goal,
        tools=tools,
    )

    def on_output(text):
        _add("server", text)
        brain.enqueue_output(text)

    def on_user_input(text):
        _add("operator", f"[Operator]: {text}")
        brain.enqueue_instruction(text)

    if sys.stdin.isatty():
        tui = MooTUI(on_user_input=on_user_input)

    if prior_goal:
        _add("system", f"Resuming from prior session. Last goal: {prior_goal}")
    _add("system", f"Connecting to {config.ssh.host}:{config.ssh.port} as {config.ssh.user}...")

    try:
        await conn.connect(on_output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    _add("system", f"Connected. Soul loaded: {soul.name or '(unnamed)'}")
    if startup_delay > 0:
        _add("system", f"Startup delay: waiting {startup_delay:.0f}s before first LLM cycle...")
        await asyncio.sleep(startup_delay)
    brain.enqueue_output("Connected")

    tasks = [asyncio.create_task(brain.run())]
    if tui is not None:
        tasks.append(asyncio.create_task(tui.run()))
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # pylint: disable=broad-exception-caught
                    pass
        await conn.disconnect()
        log_file.close()


def cmd_run(args) -> None:
    config_dir = Path(args.config_dir)
    try:
        config = load_config_dir(config_dir)
        soul = parse_soul(config_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_agent(config, soul, config_dir, startup_delay=args.delay))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="moo-agent",
        description="Autonomous persona-driven agent for DjangoMOO.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init subcommand
    init_p = sub.add_parser("init", help="Create a new agent configuration directory.")
    init_p.add_argument(
        "--output-dir",
        default="./moo-agent-config",
        metavar="DIR",
        help="Directory to write config files (default: ./moo-agent-config)",
    )
    init_p.add_argument("--name", default="Agent", metavar="NAME", help="Agent's in-world name (default: Agent)")
    init_p.add_argument("--host", default="localhost", help="SSH host (default: localhost)")
    init_p.add_argument("--port", type=int, default=8022, help="SSH port (default: 8022)")
    init_p.add_argument("--user", default="wizard", help="SSH username (default: wizard)")
    init_p.add_argument(
        "--api-key-env",
        default="ANTHROPIC_API_KEY",
        metavar="ENV_VAR",
        help="Environment variable holding the Anthropic API key",
    )
    init_p.add_argument("--force", action="store_true", help="Overwrite existing config files")
    init_p.set_defaults(func=cmd_init)

    # run subcommand
    run_p = sub.add_parser("run", help="Run the agent.")
    run_p.add_argument("config_dir", metavar="CONFIG_DIR", help="Path to the agent configuration directory")
    run_p.add_argument(
        "--delay",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="Wait this many seconds after connecting before firing the first LLM cycle (default: 0)",
    )
    run_p.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
