"""Settings.toml loading and validation."""

import os
import tomllib
from dataclasses import dataclass, field
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
    stall_timeout_seconds: int = 0  # 0 = off; Foreman uses 300
    timer_only: bool = False
    clear_window_on_wakeup: bool = True
    temperature: float | None = None  # None = provider default
    top_p: float | None = None  # None = provider default
    top_k: int | None = None  # None = provider default
    repeat_penalty: float | None = None  # None = provider default; >1 fights token loops
    min_p: float | None = None  # None = provider default; trims the low-probability tail
    structured_output_retries: int = (
        2  # PydanticAI re-ask attempts on schema validation failure; bump to 3 for local models
    )
    # Hard cap on the number of tool calls inside one ``agent.run()``. PydanticAI's
    # default has no tool-call cap; a confused local model can call ``respond()``
    # 30+ times in one cycle. 40 fits a full room build (create + describe +
    # alias + obvious + place across several objects); agents that only page
    # (Foreman) can lower this to 5 in settings.toml.
    tool_calls_per_cycle: int = 40
    tools: list[str] = field(default_factory=list)
    token_chain: list[str] = field(default_factory=list)
    use_baseline: bool = True


@dataclass
class LoreConfig:
    enabled: bool = False
    endpoint: str = ""
    verify_tls: bool = False  # krustylu's dev cert is self-signed
    max_lines: int = 4  # per-section line cap in a brief
    max_chars: int = 600  # description-summary char cap


@dataclass
class Config:
    ssh: SSHConfig
    llm: LLMConfig
    agent: AgentConfig
    soul_path: Path
    lore: LoreConfig = field(default_factory=LoreConfig)


def load_config_dir(path: str | Path) -> Config:
    """
    Load settings.toml and verify SOUL.md exists. Raises FileNotFoundError
    or ValueError on missing/malformed input.
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
            timer_only=bool(raw["agent"].get("timer_only", False)),
            clear_window_on_wakeup=bool(raw["agent"].get("clear_window_on_wakeup", True)),
            temperature=float(raw["agent"]["temperature"]) if "temperature" in raw["agent"] else None,
            top_p=float(raw["agent"]["top_p"]) if "top_p" in raw["agent"] else None,
            top_k=int(raw["agent"]["top_k"]) if "top_k" in raw["agent"] else None,
            repeat_penalty=float(raw["agent"]["repeat_penalty"]) if "repeat_penalty" in raw["agent"] else None,
            min_p=float(raw["agent"]["min_p"]) if "min_p" in raw["agent"] else None,
            structured_output_retries=int(raw["agent"].get("structured_output_retries", 2)),
            tool_calls_per_cycle=int(raw["agent"].get("tool_calls_per_cycle", 40)),
            tools=list(raw["agent"].get("tools", [])),
            token_chain=list(raw["agent"].get("token_chain", [])),
            use_baseline=bool(raw["agent"].get("use_baseline", True)),
        )
        if env_chain := os.environ.get("MOO_TOKEN_CHAIN"):
            agent.token_chain = [a.strip() for a in env_chain.split(",") if a.strip()]
        raw_lore = raw.get("lore", {})
        lore = LoreConfig(
            enabled=bool(raw_lore.get("enabled", False)),
            endpoint=raw_lore.get("endpoint", ""),
            verify_tls=bool(raw_lore.get("verify_tls", False)),
            max_lines=int(raw_lore.get("max_lines", 4)),
            max_chars=int(raw_lore.get("max_chars", 600)),
        )
    except KeyError as e:
        raise ValueError(f"Missing required field in settings.toml: {e}") from e

    return Config(ssh=ssh, llm=llm, agent=agent, soul_path=soul_path, lore=lore)
