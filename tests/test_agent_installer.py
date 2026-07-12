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
