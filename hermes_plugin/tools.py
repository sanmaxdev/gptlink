"""Handlers for the GPTLink Hermes plugin."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
OPERATOR = PLUGIN_ROOT / "hermes_plugin" / "lifecycle.py"
IMAGE_CLIENT = PLUGIN_ROOT / "hermes_plugin" / "image_client.py"
ACTION_MAP = {
    "setup": "setup",
    "auth_complete": "auth-complete",
    "ensure": "ensure",
    "status": "status",
    "restart": "restart",
    "update": "update",
    "rotate_key": "rotate-key",
    "logs": "logs",
}


def _execute(script: Path, arguments: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *arguments],
        text=True,
        capture_output=True,
        timeout=timeout,
        cwd=PLUGIN_ROOT,
    )


def _json_result(result: subprocess.CompletedProcess[str]) -> dict:
    output = (result.stdout or "").strip()
    if result.returncode:
        return {"state": "error", "message": output or (result.stderr or "GPTLink command failed").strip()}
    try:
        value = json.loads(output)
        return value if isinstance(value, dict) else {"state": "error", "message": output}
    except json.JSONDecodeError:
        return {"state": "ok", "output": output}


def manage(args: dict, **kwargs) -> str:
    del kwargs
    try:
        action = str(args.get("action", "")).strip()
        command = ACTION_MAP.get(action)
        if not command:
            return json.dumps({"state": "error", "message": "Unsupported management action"})
        result = _execute(OPERATOR, [command], timeout=900 if command in {"setup", "update"} else 120)
        return json.dumps(_json_result(result))
    except Exception as exc:
        return json.dumps({"state": "error", "message": str(exc)})


def generate(args: dict, **kwargs) -> str:
    del kwargs
    try:
        prompt = str(args.get("prompt", "")).strip()
        if not prompt:
            return json.dumps({"state": "error", "message": "Prompt is required"})
        ensured = _json_result(_execute(OPERATOR, ["ensure"], timeout=900))
        if ensured.get("state") != "ready":
            return json.dumps(ensured)

        image_format = str(args.get("format", "png"))
        extension = "jpg" if image_format == "jpeg" else image_format
        hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
        output = hermes_home / "cache" / "images" / f"gptlink_{uuid.uuid4().hex}.{extension}"
        command = [
            prompt,
            "--aspect-ratio", str(args.get("aspect_ratio", "1:1")),
            "--quality", str(args.get("quality", "auto")),
            "--format", image_format,
            "--output", str(output),
        ]
        references = args.get("reference_paths") or []
        if not isinstance(references, list) or len(references) > 16:
            return json.dumps({"state": "error", "message": "reference_paths must contain at most 16 paths"})
        for reference in references:
            command.extend(["--reference", str(reference)])
        generated = _execute(IMAGE_CLIENT, command, timeout=420)
        if generated.returncode:
            return json.dumps({
                "state": "error",
                "message": (generated.stderr or generated.stdout or "Image generation failed").strip(),
            })
        path = (generated.stdout or "").strip()
        return json.dumps({
            "state": "completed",
            "image": path,
            "prompt": prompt,
            "aspect_ratio": str(args.get("aspect_ratio", "1:1")),
            "quality": str(args.get("quality", "auto")),
            "format": image_format,
        })
    except Exception as exc:
        return json.dumps({"state": "error", "message": str(exc)})
