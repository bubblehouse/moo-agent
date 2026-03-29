"""
Tests for moo/agent/config.py.

These tests do not require DJANGO_SETTINGS_MODULE and do not import from moo.core.
"""

import pytest

from moo.agent.config import load_config_dir

VALID_TOML = """\
[ssh]
host = "localhost"
port = 8022
user = "wizard"
password = "secret"
key_file = ""

[llm]
provider = "anthropic"
model = "claude-opus-4-6"
api_key_env = "ANTHROPIC_API_KEY"

[agent]
command_rate_per_second = 1.0
memory_window_lines = 50
"""


def _write_valid_config(tmp_path):
    (tmp_path / "settings.toml").write_text(VALID_TOML)
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n")
    return tmp_path


def test_load_config_all_fields(tmp_path):
    _write_valid_config(tmp_path)
    config = load_config_dir(tmp_path)
    assert config.ssh.host == "localhost"
    assert config.ssh.port == 8022
    assert config.ssh.user == "wizard"
    assert config.ssh.password == "secret"
    assert config.ssh.key_file == ""
    assert config.llm.provider == "anthropic"
    assert config.llm.model == "claude-opus-4-6"
    assert config.llm.api_key_env == "ANTHROPIC_API_KEY"
    assert config.llm.aws_region == "us-east-1"
    assert config.agent.command_rate_per_second == 1.0
    assert config.agent.memory_window_lines == 50
    assert config.agent.idle_wakeup_seconds == 60.0
    assert config.soul_path.name == "SOUL.md"


def test_idle_wakeup_seconds_defaults_to_60(tmp_path):
    """TOML without idle_wakeup_seconds uses the 60.0 default."""
    _write_valid_config(tmp_path)
    config = load_config_dir(tmp_path)
    assert config.agent.idle_wakeup_seconds == 60.0


def test_idle_wakeup_seconds_reads_from_toml(tmp_path):
    toml = VALID_TOML + "idle_wakeup_seconds = 30.0\n"
    (tmp_path / "settings.toml").write_text(toml)
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n")
    config = load_config_dir(tmp_path)
    assert config.agent.idle_wakeup_seconds == 30.0


def test_load_config_soul_path_points_to_soul_md(tmp_path):
    _write_valid_config(tmp_path)
    config = load_config_dir(tmp_path)
    assert config.soul_path.exists()
    assert config.soul_path.name == "SOUL.md"


def test_missing_settings_toml_raises(tmp_path):
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n")
    with pytest.raises(FileNotFoundError, match="settings.toml"):
        load_config_dir(tmp_path)


def test_missing_soul_md_raises(tmp_path):
    (tmp_path / "settings.toml").write_text(VALID_TOML)
    with pytest.raises(FileNotFoundError, match="SOUL.md"):
        load_config_dir(tmp_path)


def test_malformed_toml_raises_value_error(tmp_path):
    (tmp_path / "settings.toml").write_text("this is not valid toml ][")
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n")
    with pytest.raises(ValueError, match="Malformed settings.toml"):
        load_config_dir(tmp_path)


def test_missing_required_field_raises_value_error(tmp_path):
    broken = "[ssh]\nhost = 'localhost'\n"  # missing port, user, and other sections
    (tmp_path / "settings.toml").write_text(broken)
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n")
    with pytest.raises(ValueError, match="Missing required field"):
        load_config_dir(tmp_path)


def test_accepts_path_string(tmp_path):
    _write_valid_config(tmp_path)
    config = load_config_dir(str(tmp_path))
    assert config.ssh.host == "localhost"


def test_bedrock_config(tmp_path):
    """Bedrock provider with aws_region; api_key_env is optional."""
    toml = """\
[ssh]
host = "localhost"
port = 8022
user = "wizard"

[llm]
provider = "bedrock"
model = "us.anthropic.claude-sonnet-4-5-20251001-v1:0"
aws_region = "us-west-2"

[agent]
command_rate_per_second = 1.0
memory_window_lines = 50
"""
    (tmp_path / "settings.toml").write_text(toml)
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n")
    config = load_config_dir(tmp_path)
    assert config.llm.provider == "bedrock"
    assert config.llm.aws_region == "us-west-2"
    assert config.llm.api_key_env == "ANTHROPIC_API_KEY"  # default


def test_api_key_env_defaults_when_absent(tmp_path):
    """api_key_env is optional; defaults to ANTHROPIC_API_KEY."""
    toml = """\
[ssh]
host = "localhost"
port = 8022
user = "wizard"

[llm]
provider = "anthropic"
model = "claude-opus-4-6"

[agent]
command_rate_per_second = 1.0
memory_window_lines = 50
"""
    (tmp_path / "settings.toml").write_text(toml)
    (tmp_path / "SOUL.md").write_text("# Name\nTest\n")
    config = load_config_dir(tmp_path)
    assert config.llm.api_key_env == "ANTHROPIC_API_KEY"
