import base64
import importlib.util
import json
import time
from pathlib import Path


def load_operator():
    path = Path(__file__).parents[1] / "skills/gptlink-image/scripts/gptlink_operator.py"
    spec = importlib.util.spec_from_file_location("gptlink_operator_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def token(expires: int) -> str:
    part = base64.urlsafe_b64encode(json.dumps({"exp": expires}).encode()).decode().rstrip("=")
    return f"e30.{part}.signature"


def test_operator_detects_existing_hermes_codex_auth(tmp_path, monkeypatch) -> None:
    operator = load_operator()
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / "auth.json").write_text(json.dumps({
        "providers": {
            "openai-codex": {"tokens": {"access_token": token(int(time.time()) + 3600)}}
        }
    }))
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))

    assert operator.auth_source() == "hermes"


def test_operator_rejects_expired_hermes_codex_auth(tmp_path, monkeypatch) -> None:
    operator = load_operator()
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    (hermes_home / "auth.json").write_text(json.dumps({
        "providers": {
            "openai-codex": {"tokens": {"access_token": token(int(time.time()) - 60)}}
        }
    }))
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))

    assert operator.auth_source() is None
