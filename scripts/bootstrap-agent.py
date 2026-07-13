#!/usr/bin/env python3
"""Create GPTLink's environment, install dependencies, and register agent integrations."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap GPTLink and connect it to one or more coding agents"
    )
    parser.add_argument(
        "--agent",
        choices=["claude-code", "antigravity", "codex", "all"],
        default="all",
    )
    parser.add_argument("--scope", choices=["user", "project"], default="user")
    parser.add_argument("--mode", choices=["local", "remote"], default="local")
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--allowed-root", action="append", type=Path, default=[])
    parser.add_argument("--url", help="Remote GPTLink origin, such as https://images.example.com")
    parser.add_argument("--api-key", default=os.environ.get("GPTLINK_API_KEY"))
    args = parser.parse_args()

    if sys.version_info < (3, 11):
        parser.error("GPTLink requires Python 3.11 or newer")
    if args.mode == "remote" and (not args.url or not args.api_key):
        parser.error("remote mode requires --url and GPTLINK_API_KEY (or --api-key)")

    python = venv_python()
    if not python.is_file():
        run([sys.executable, "-m", "venv", str(VENV)])
    run([
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--quiet",
        "-r",
        str(ROOT / "requirements.txt"),
    ])

    command = [
        str(python),
        str(ROOT / "scripts" / "install-agent.py"),
        "--agent",
        args.agent,
        "--scope",
        args.scope,
        "--mode",
        args.mode,
        "--workspace",
        str(args.workspace.expanduser().resolve()),
    ]
    for allowed_root in args.allowed_root:
        command.extend(["--allowed-root", str(allowed_root.expanduser().resolve())])
    if args.url:
        command.extend(["--url", args.url])
    environment = os.environ.copy()
    if args.api_key:
        environment["GPTLINK_API_KEY"] = args.api_key
    result = subprocess.run(command, cwd=ROOT, env=environment)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
