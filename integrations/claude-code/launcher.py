from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    plugin_root = Path(__file__).resolve().parent
    candidates = [
        Path(os.environ["GPTLINK_ROOT"]).expanduser() if os.environ.get("GPTLINK_ROOT") else None,
        Path("/opt/gptlink"),
        plugin_root.parents[1],
    ]
    for root in candidates:
        if root and (root / "gptlink" / "mcp_server.py").is_file():
            os.chdir(root)
            python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            executable = python if python.is_file() else Path(os.sys.executable)
            os.execv(str(executable), [str(executable), "-m", "gptlink.mcp_server", "--transport", "stdio"])
    raise SystemExit("GPTLink was not found. Set GPTLINK_ROOT to the cloned repository path.")


if __name__ == "__main__":
    main()
