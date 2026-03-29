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
import sys
from pathlib import Path

from moo.agent.brain import Brain
from moo.agent.config import load_config_dir
from moo.agent.connection import MooConnection
from moo.agent.soul import parse_soul
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


async def run_agent(config, soul, config_dir: Path) -> None:
    logs_dir = config_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    session_ts = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_path = logs_dir / f"{session_ts}.log"
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: WPS515

    conn = MooConnection(config.ssh)
    tui: MooTUI | None = None

    def _add(kind, text):
        entry = LogEntry(kind=kind, text=text)
        if tui is not None:
            tui.add_entry(entry)
        log_file.write(f"[{entry.timestamp}] [{kind}] {text}\n")
        log_file.flush()

    brain = Brain(
        soul=soul,
        config=config,
        send_command=lambda cmd: (conn.send(cmd), _add("action", cmd)),
        on_thought=lambda t: _add("thought", t),
        config_dir=config_dir,
        on_status_change=lambda s: tui.set_status(s) if tui is not None else None,
    )

    def on_output(text):
        _add("server", text)
        brain.enqueue_output(text)

    def on_user_input(text):
        _add("system", f"[Operator]: {text}")
        brain.enqueue_instruction(text)

    tui = MooTUI(on_user_input=on_user_input)

    _add("system", f"Connecting to {config.ssh.host}:{config.ssh.port} as {config.ssh.user}...")

    try:
        await conn.connect(on_output)
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    _add("system", f"Connected. Soul loaded: {soul.name or '(unnamed)'}")
    brain.enqueue_output("Connected")

    try:
        await asyncio.gather(tui.run(), brain.run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
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

    asyncio.run(run_agent(config, soul, config_dir))


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
    run_p.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
