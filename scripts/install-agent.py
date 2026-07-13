#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SKILL_SOURCE = ROOT / "integrations" / "shared" / "gptlink-images"


def merge_server(path: Path, server: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            value = {}
    except (OSError, json.JSONDecodeError):
        value = {}
    servers = value.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise RuntimeError(f"mcpServers is not an object in {path}")
    servers["gptlink"] = server
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def copy_skill(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SKILL_SOURCE, destination, dirs_exist_ok=True)


def local_server(allowed_roots: list[Path]) -> dict[str, Any]:
    user_data = Path.home() / ".local" / "share" / "gptlink"
    env = {
        "GPTLINK_MCP_ALLOWED_ROOTS": os.pathsep.join(str(path) for path in allowed_roots),
        "GPTLINK_DATA_DIR": str(user_data),
    }
    return {
        "command": str(Path(sys.executable).resolve()),
        "args": ["-m", "gptlink.mcp_server", "--transport", "stdio"],
        "cwd": str(ROOT),
        "env": env,
    }


def remote_server(url: str, api_key: str) -> dict[str, Any]:
    if not url.startswith("https://") and not url.startswith("http://127.0.0.1"):
        raise RuntimeError("Remote MCP URLs must use HTTPS")
    return {
        "serverUrl": url.rstrip("/") + "/mcp/",
        "headers": {"Authorization": f"Bearer {api_key}"},
    }


def install_claude(server: dict[str, Any], scope: str, workspace: Path) -> Path:
    if scope == "project":
        config = workspace / ".mcp.json"
        skill = workspace / ".claude" / "skills" / "gptlink-images"
    else:
        config = Path.home() / ".claude.json"
        skill = Path.home() / ".claude" / "skills" / "gptlink-images"
    claude = shutil.which("claude")
    if claude:
        subprocess.run(
            [claude, "mcp", "remove", "--scope", scope, "gptlink"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        if "serverUrl" in server:
            command = [
                claude, "mcp", "add", "--scope", scope, "--transport", "http",
                "gptlink", str(server["serverUrl"]),
                "--header", f"Authorization: {server['headers']['Authorization']}",
            ]
        else:
            command = [claude, "mcp", "add", "--scope", scope, "gptlink"]
            for key, value in server.get("env", {}).items():
                command.extend(["--env", f"{key}={value}"])
            command.extend(["--", server["command"], *server["args"]])
        run_checked(command, cwd=workspace)
    else:
        # Project .mcp.json is a documented portable fallback. User scope needs the CLI.
        if scope != "project":
            raise RuntimeError("Claude Code CLI was not found in PATH")
        claude_server = dict(server)
        if "serverUrl" in claude_server:
            claude_server["url"] = claude_server.pop("serverUrl")
            claude_server["type"] = "http"
        merge_server(config, claude_server)
    copy_skill(skill)
    return config


def install_antigravity(server: dict[str, Any], scope: str, workspace: Path) -> Path:
    if scope == "project":
        config = workspace / ".agents" / "mcp_config.json"
        plugin = workspace / ".agents" / "plugins" / "gptlink"
    else:
        config = Path.home() / ".gemini" / "config" / "mcp_config.json"
        plugin = Path.home() / ".gemini" / "config" / "plugins" / "gptlink"
    merge_server(config, server)
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "plugin.json").write_text(
        json.dumps({
            "$schema": "https://antigravity.google/schemas/v1/plugin.json",
            "name": "gptlink",
            "description": "Generate and edit images with GPTLink MCP.",
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    copy_skill(plugin / "skills" / "gptlink-images")
    return config


def run_checked(command: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())


def install_codex(
    server: dict[str, Any], scope: str, workspace: Path, api_key: str | None
) -> str:
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI was not found in PATH")
    if scope != "user":
        raise RuntimeError("Codex installation currently uses user scope; rerun with --scope user")
    subprocess.run([codex, "mcp", "remove", "gptlink"], capture_output=True, text=True)
    if "serverUrl" in server:
        if not api_key:
            raise RuntimeError("A GPTLink API key is required for remote mode")
        os.environ["GPTLINK_API_KEY"] = api_key
        run_checked([
            codex, "mcp", "add", "gptlink", "--url", str(server["serverUrl"]),
            "--bearer-token-env-var", "GPTLINK_API_KEY",
        ])
    else:
        command = [codex, "mcp", "add", "gptlink"]
        for key, value in server.get("env", {}).items():
            command.extend(["--env", f"{key}={value}"])
        command.extend(["--", server["command"], *server["args"]])
        run_checked(command)
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    copy_skill(codex_home / "skills" / "gptlink-images")
    return str(codex_home / "config.toml")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install GPTLink MCP and its image skill into coding agents"
    )
    parser.add_argument(
        "--agent", choices=["claude-code", "antigravity", "codex", "all"], default="all"
    )
    parser.add_argument("--scope", choices=["user", "project"], default="user")
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--allowed-root", action="append", type=Path, default=[])
    parser.add_argument("--url", help="Remote GPTLink base URL, for example https://images.example.com")
    parser.add_argument("--api-key", default=os.environ.get("GPTLINK_API_KEY"))
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    roots = [path.expanduser().resolve() for path in args.allowed_root]
    if not roots:
        roots = [workspace if args.scope == "project" else Path.home().resolve()]
    if args.mode == "remote":
        if not args.url or not args.api_key:
            parser.error("remote mode requires --url and --api-key (or GPTLINK_API_KEY)")
        server = remote_server(args.url, args.api_key)
    else:
        server = local_server(roots)

    agents = (
        ["claude-code", "antigravity", "codex"] if args.agent == "all" else [args.agent]
    )
    installed: dict[str, str] = {}
    failures: dict[str, str] = {}
    for agent in agents:
        try:
            if agent == "claude-code":
                installed[agent] = str(install_claude(server, args.scope, workspace))
            elif agent == "antigravity":
                installed[agent] = str(install_antigravity(server, args.scope, workspace))
            else:
                installed[agent] = install_codex(server, args.scope, workspace, args.api_key)
        except RuntimeError as exc:
            failures[agent] = str(exc)

    print(json.dumps({
        "state": "ready" if installed and not failures else "partial" if installed else "error",
        "mode": args.mode,
        "installed": installed,
        "failed": failures,
        "next_step": (
            "Restart or reload the agent, call gptlink_status, and complete Codex "
            "device login only if authentication is missing."
        ),
    }, indent=2))
    if not installed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
