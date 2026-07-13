import importlib.util
import json
from pathlib import Path

import pytest


def load_installer():
    path = Path(__file__).parents[1] / "scripts" / "install-agent.py"
    spec = importlib.util.spec_from_file_location("gptlink_agent_installer", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_merge_server_preserves_existing_configuration(tmp_path: Path) -> None:
    installer = load_installer()
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {"existing": {"command": "tool"}}}))

    installer.merge_server(config, {"command": "python", "args": []})
    value = json.loads(config.read_text())

    assert set(value["mcpServers"]) == {"existing", "gptlink"}


def test_remote_server_requires_https_except_loopback() -> None:
    installer = load_installer()

    with pytest.raises(RuntimeError, match="must use HTTPS"):
        installer.remote_server("http://example.com", "secret")
    assert installer.remote_server("https://images.example.com", "secret")["serverUrl"].endswith("/mcp/")


def test_opencode_project_install_preserves_config_and_installs_skill(
    tmp_path: Path,
) -> None:
    installer = load_installer()
    config = tmp_path / "opencode.json"
    config.write_text(
        json.dumps({"$schema": "https://opencode.ai/config.json", "mcp": {"existing": {"type": "remote"}}})
    )
    server = {
        "command": "/opt/gptlink/.venv/bin/python",
        "args": ["-m", "gptlink.mcp_server", "--transport", "stdio"],
        "env": {"GPTLINK_DATA_DIR": "/tmp/gptlink"},
    }

    installed = installer.install_opencode(server, "project", tmp_path)
    value = json.loads(config.read_text())

    assert installed == config
    assert set(value["mcp"]) == {"existing", "gptlink"}
    assert value["mcp"]["gptlink"]["type"] == "local"
    assert value["mcp"]["gptlink"]["environment"]["PYTHONPATH"] == str(installer.ROOT)
    assert (tmp_path / ".opencode" / "skills" / "gptlink-images" / "SKILL.md").is_file()


def test_opencode_remote_server_uses_supported_shape(tmp_path: Path) -> None:
    installer = load_installer()

    installer.install_opencode(
        installer.remote_server("https://images.example.com", "secret"),
        "project",
        tmp_path,
    )
    server = json.loads((tmp_path / "opencode.json").read_text())["mcp"]["gptlink"]

    assert server == {
        "type": "remote",
        "url": "https://images.example.com/mcp/",
        "enabled": True,
        "oauth": False,
        "headers": {"Authorization": "Bearer secret"},
    }
