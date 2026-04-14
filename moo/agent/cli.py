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
import signal
import sys
from pathlib import Path

from moo.agent.brain import Brain, looks_like_error
from moo.agent.config import load_config_dir
from moo.agent.connection import MooConnection
from moo.agent.session_log import read_prior_session
from moo.agent.soul import parse_soul
from moo.agent.tools import BUILDER_TOOLS_BY_NAME
from moo.agent.tui import LogEntry, MooTUI


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

    prior_summary, prior_goal = read_prior_session(logs_dir, log_path)

    # Timer-based agents (idle_wakeup_seconds > 0) start completely fresh —
    # no prior goal, no prior summary. Stale context causes them to skip
    # mandatory first steps (e.g. mailmen skipping @mail listing).
    #
    # Page-triggered agents (idle_wakeup_seconds == 0) also discard the prior
    # summary. The 40-line prior-session dump injects stale loop behavior and
    # wrong world state into every new session, causing more harm than good.
    # The prior_goal is kept only to feed the auto-reconnect page mechanism
    # (prior_goal_for_reconnect in Brain.__init__) — it is never set as the
    # agent's current_goal for page-triggered agents.
    if config.agent.idle_wakeup_seconds > 0:
        prior_summary = ""
        prior_goal = ""
    else:
        prior_summary = ""

    conn = MooConnection(config.ssh)
    tui: MooTUI | None = None
    _disconnect_event = asyncio.Event()

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
        tui = MooTUI(on_user_input=on_user_input, agent_name=config.ssh.user or "")

    # Only inject prior goal for page-triggered agents (idle_wakeup_seconds=0).
    # Timer-based agents (mailmen etc.) should start fresh each run — stale goals
    # cause them to skip mandatory first steps like @mail.
    if prior_goal and config.agent.idle_wakeup_seconds == 0:
        _add("system", f"Resuming from prior session. Last goal: {prior_goal}")
    _add("system", f"Connecting to {config.ssh.host}:{config.ssh.port} as {config.ssh.user}...")

    conn.set_disconnect_callback(_disconnect_event.set)

    async def _reconnect_watcher():
        """Detect dropped SSH connections and transparently reconnect."""
        while True:
            await _disconnect_event.wait()
            _disconnect_event.clear()
            _add("system", "Connection lost — reconnecting in 5s...")
            await asyncio.sleep(5)
            for attempt in range(1, 6):
                try:
                    await conn.connect(on_output)
                    _add("system", f"Reconnected. Soul: {soul.name or '(unnamed)'}")
                    brain.enqueue_output("Connected")
                    break
                except Exception as e:  # pylint: disable=broad-exception-caught
                    _add("system", f"Reconnect attempt {attempt}/5 failed: {e}")
                    await asyncio.sleep(min(30, 5 * attempt))

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

    tasks = [asyncio.create_task(brain.run()), asyncio.create_task(_reconnect_watcher())]
    if tui is not None:
        tasks.append(asyncio.create_task(tui.run()))

    # Graceful SIGTERM: cancel tasks so the finally block can send @quit cleanly.
    # Without this, SIGTERM kills the process before conn.disconnect() runs,
    # leaving a zombie server-side session that blocks the next reconnect.
    _tasks_ref = tasks
    loop = asyncio.get_running_loop()

    def _sigterm_handler():
        for t in _tasks_ref:
            if not t.done():
                t.cancel()

    loop.add_signal_handler(signal.SIGTERM, _sigterm_handler)

    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
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
