import importlib.util
from pathlib import Path


def load_bootstrap():
    path = Path(__file__).parents[1] / "scripts" / "bootstrap-agent.py"
    spec = importlib.util.spec_from_file_location("gptlink_agent_bootstrap", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_uses_platform_virtual_environment_python() -> None:
    bootstrap = load_bootstrap()

    path = bootstrap.venv_python()

    assert bootstrap.VENV in path.parents
    assert path.name in {"python", "python.exe"}
