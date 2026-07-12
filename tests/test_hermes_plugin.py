import importlib.util
import json
from pathlib import Path
import sys

from hermes_plugin import schemas, tools


class StubContext:
    def __init__(self) -> None:
        self.tools = {}
        self.skills = {}

    def register_tool(self, *, name, toolset, schema, handler, description):
        self.tools[name] = {
            "toolset": toolset,
            "schema": schema,
            "handler": handler,
            "description": description,
        }

    def register_skill(self, name, path):
        self.skills[name] = Path(path)


def load_root_plugin():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "gptlink_plugin_test", root / "__init__.py", submodule_search_locations=[str(root)]
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_plugin_registers_tools_and_bundled_skill() -> None:
    plugin = load_root_plugin()
    context = StubContext()

    plugin.register(context)

    assert set(context.tools) == {"gptlink_manage", "gptlink_generate"}
    assert context.tools["gptlink_generate"]["toolset"] == "gptlink"
    assert context.skills["gptlink-image"].is_file()


def test_tool_schemas_match_handlers() -> None:
    assert schemas.MANAGE["name"] == "gptlink_manage"
    assert schemas.GENERATE["name"] == "gptlink_generate"
    result = json.loads(tools.generate({"prompt": ""}))
    assert result["state"] == "error"
