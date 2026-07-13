import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def read_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_all_committed_mcp_templates_are_valid_json() -> None:
    templates = [
        "integrations/antigravity/mcp_config.json",
        "integrations/claude-code/.mcp.json",
        "integrations/generic/remote.json",
        "integrations/generic/stdio.json",
        "integrations/opencode/local.json",
        "integrations/opencode/remote.json",
    ]

    for template in templates:
        assert isinstance(read_json(template), dict), template


def test_opencode_templates_follow_current_schema_shape() -> None:
    local = read_json("integrations/opencode/local.json")["mcp"]["gptlink"]
    remote = read_json("integrations/opencode/remote.json")["mcp"]["gptlink"]

    assert local["type"] == "local"
    assert isinstance(local["command"], list)
    assert local["environment"]["PYTHONPATH"]
    assert remote["type"] == "remote"
    assert remote["oauth"] is False
    assert remote["url"].endswith("/mcp/")
    assert remote["headers"]["Authorization"].startswith("Bearer ")
