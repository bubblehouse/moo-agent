"""
Configuration loading for moo-agent.

Reads settings.toml from a config directory and validates all required fields.
Does not import from moo.core or trigger Django setup.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SSHConfig:
    host: str
    port: int
    user: str
    password: str
    key_file: str


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key_env: str = "ANTHROPIC_API_KEY"
    aws_region: str = "us-east-1"
    base_url: str = ""


@dataclass
class AgentConfig:
    command_rate_per_second: float
    memory_window_lines: int
    idle_wakeup_seconds: float = 60.0
    max_tokens: int = 2048
    stall_timeout_seconds: int = 0  # 0 = disabled; Foreman uses 300
    tools: list[str] = None  # type: ignore[assignment]
    token_chain: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.tools is None:
            self.tools = []
        if self.token_chain is None:
            self.token_chain = []


@dataclass
class Config:
    ssh: SSHConfig
    llm: LLMConfig
    agent: AgentConfig
    soul_path: Path


def load_config_dir(path: str | Path) -> Config:
    """
    Load and validate agent configuration from a directory.

    Reads settings.toml and checks that SOUL.md exists. Raises FileNotFoundError
    if either file is missing, ValueError if the TOML is malformed or missing
    required sections.
    """
    config_dir = Path(path)
    toml_path = config_dir / "settings.toml"
    soul_path = config_dir / "SOUL.md"

    if not toml_path.exists():
        raise FileNotFoundError(f"settings.toml not found in {config_dir}")
    if not soul_path.exists():
        raise FileNotFoundError(f"SOUL.md not found in {config_dir}")

    try:
        with open(toml_path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"Malformed settings.toml: {e}") from e

    try:
        ssh = SSHConfig(
            host=raw["ssh"]["host"],
            port=int(raw["ssh"]["port"]),
            user=raw["ssh"]["user"],
            password=raw["ssh"].get("password", ""),
            key_file=raw["ssh"].get("key_file", ""),
        )
        llm = LLMConfig(
            provider=raw["llm"]["provider"],
            model=raw["llm"]["model"],
            api_key_env=raw["llm"].get("api_key_env", "ANTHROPIC_API_KEY"),
            aws_region=raw["llm"].get("aws_region", "us-east-1"),
            base_url=raw["llm"].get("base_url", ""),
        )
        agent = AgentConfig(
            command_rate_per_second=float(raw["agent"]["command_rate_per_second"]),
            memory_window_lines=int(raw["agent"]["memory_window_lines"]),
            idle_wakeup_seconds=float(raw["agent"].get("idle_wakeup_seconds", 60.0)),
            max_tokens=int(raw["agent"].get("max_tokens", 2048)),
            stall_timeout_seconds=int(raw["agent"].get("stall_timeout_seconds", 0)),
            tools=list(raw["agent"].get("tools", [])),
            token_chain=list(raw["agent"].get("token_chain", [])),
        )
    except KeyError as e:
        raise ValueError(f"Missing required field in settings.toml: {e}") from e

    return Config(ssh=ssh, llm=llm, agent=agent, soul_path=soul_path)
