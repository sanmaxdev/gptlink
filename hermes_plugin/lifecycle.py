#!/usr/bin/env python3
"""Autonomous user-space lifecycle manager for the GPTLink plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import base64

HOME = pathlib.Path.home()
APP_DIR = pathlib.Path(os.environ.get("GPTLINK_INSTALL_DIR", HOME / ".local/share/gptlink"))
DATA_DIR = pathlib.Path(os.environ.get("GPTLINK_DATA_DIR", HOME / ".local/share/gptlink-data"))
STATE_DIR = pathlib.Path(os.environ.get("GPTLINK_SKILL_STATE", HOME / ".local/state/gptlink-skill"))
CONFIG_DIR = pathlib.Path(os.environ.get("GPTLINK_CONFIG_DIR", HOME / ".config/gptlink"))
CONFIG_FILE = CONFIG_DIR / "hermes.json"
PID_FILE = STATE_DIR / "server.pid"
LOG_FILE = STATE_DIR / "server.log"
REQUIREMENTS_HASH = STATE_DIR / "requirements.sha256"
AUTH_PENDING_FILE = STATE_DIR / "auth-pending.json"
REPO_URL = os.environ.get("GPTLINK_REPO_URL", "https://github.com/sanmaxdev/gptlink.git")
HOST = "127.0.0.1"
PORT = int(os.environ.get("GPTLINK_PORT", "8787"))
ORIGIN = f"http://{HOST}:{PORT}"


class OperatorError(RuntimeError):
    pass


def emit(state: str, **values: object) -> None:
    print(json.dumps({"state": state, **values}, indent=2))


def run(command: list[str], *, cwd: pathlib.Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise OperatorError(f"Command failed: {' '.join(command[:3])}: {detail}")
    return result


def command_path(name: str) -> str | None:
    local = HOME / ".local/bin" / name
    return str(local) if local.exists() else shutil.which(name)


def http_json(path: str, *, method: str = "GET", payload: dict | None = None,
              api_key: str | None = None, timeout: int = 15) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(f"{ORIGIN}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OperatorError(f"GPTLink HTTP {exc.code}: {detail}") from exc


def healthy() -> bool:
    try:
        return http_json("/health", timeout=2).get("status") == "ok"
    except (OSError, OperatorError, ValueError):
        return False


def install_codex() -> str:
    existing = command_path("codex")
    if existing:
        return existing
    npm = command_path("npm")
    if not npm:
        raise OperatorError("Codex CLI is missing and npm is unavailable. Install Node.js 20+ once, then retry.")
    (HOME / ".local").mkdir(parents=True, exist_ok=True)
    run([npm, "install", "--global", "--prefix", str(HOME / ".local"), "@openai/codex"])
    installed = command_path("codex")
    if not installed:
        raise OperatorError("Codex CLI installation finished but ~/.local/bin/codex was not created")
    return installed


def install_app(*, update: bool) -> None:
    if not command_path("git"):
        raise OperatorError("git is required. Install git once, then retry.")
    APP_DIR.parent.mkdir(parents=True, exist_ok=True)
    if (APP_DIR / ".git").is_dir():
        if update:
            run(["git", "pull", "--ff-only"], cwd=APP_DIR)
    elif APP_DIR.exists() and any(APP_DIR.iterdir()):
        raise OperatorError(f"Install directory exists but is not a GPTLink checkout: {APP_DIR}")
    else:
        run(["git", "clone", "--depth", "1", REPO_URL, str(APP_DIR)])

    venv_python = APP_DIR / ".venv/bin/python"
    if not venv_python.exists():
        result = subprocess.run([sys.executable, "-m", "venv", str(APP_DIR / ".venv")], text=True, capture_output=True)
        if result.returncode:
            raise OperatorError("Python venv support is missing. On Ubuntu install python3-venv once, then retry.")
    requirements = APP_DIR / "requirements.txt"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    previous = REQUIREMENTS_HASH.read_text().strip() if REQUIREMENTS_HASH.exists() else ""
    if digest != previous:
        run([str(venv_python), "-m", "pip", "install", "-r", str(requirements)])
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        REQUIREMENTS_HASH.write_text(digest)


def server_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "PATH": f"{HOME / '.local/bin'}:{env.get('PATH', '')}",
        "CODEX_HOME": str(HOME / ".codex"),
        "GPTLINK_DATA_DIR": str(DATA_DIR),
        "GPTLINK_HOST": HOST,
        "GPTLINK_PORT": str(PORT),
    })
    return env


def start_server() -> None:
    if healthy():
        return
    venv_python = APP_DIR / ".venv/bin/python"
    if not venv_python.exists():
        raise OperatorError("GPTLink is not installed; run setup first")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_FILE.open("ab", buffering=0)
    process = subprocess.Popen(
        [str(venv_python), "-m", "uvicorn", "gptlink.main:app", "--host", HOST, "--port", str(PORT)],
        cwd=APP_DIR, env=server_environment(), stdin=subprocess.DEVNULL,
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True, close_fds=True,
    )
    PID_FILE.write_text(str(process.pid))
    for _ in range(40):
        if healthy():
            return
        if process.poll() is not None:
            break
        time.sleep(0.25)
    tail = log_tail(30)
    raise OperatorError(f"GPTLink did not start. Recent log:\n{tail}")


def stop_server() -> None:
    if not PID_FILE.exists():
        return
    try:
        pid = int(PID_FILE.read_text().strip())
        cmdline = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        if "uvicorn" not in cmdline or "gptlink.main:app" not in cmdline:
            raise OperatorError("Refusing to stop a process that is not the managed GPTLink server")
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not pathlib.Path(f"/proc/{pid}").exists():
                break
            time.sleep(0.1)
    except ProcessLookupError:
        pass
    finally:
        PID_FILE.unlink(missing_ok=True)


def account() -> dict | None:
    try:
        status = http_json("/api/status")
        value = status.get("codex", {}).get("account")
        return value if isinstance(value, dict) and value.get("type") == "chatgpt" else None
    except (OperatorError, AttributeError):
        return None


def fresh_token(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        segment = value.split(".")[1]
        segment += "=" * (-len(segment) % 4)
        claims = json.loads(base64.urlsafe_b64decode(segment))
        expires = claims.get("exp") if isinstance(claims, dict) else None
        return not isinstance(expires, (int, float)) or expires > time.time() + 60
    except (IndexError, ValueError, json.JSONDecodeError):
        return True


def auth_source() -> str | None:
    codex_auth = pathlib.Path(os.environ.get("CODEX_HOME", HOME / ".codex")) / "auth.json"
    try:
        value = json.loads(codex_auth.read_text())
        if fresh_token((value.get("tokens") or {}).get("access_token")):
            return "codex_cli"
    except (OSError, json.JSONDecodeError, AttributeError):
        pass

    hermes_home = pathlib.Path(os.environ.get("HERMES_HOME", HOME / ".hermes"))
    try:
        value = json.loads((hermes_home / "auth.json").read_text())
        provider = (value.get("providers") or {}).get("openai-codex") or {}
        if fresh_token((provider.get("tokens") or {}).get("access_token")):
            return "hermes"
        pool = (value.get("credential_pool") or {}).get("openai-codex") or []
        for entry in pool if isinstance(pool, list) else []:
            if not isinstance(entry, dict):
                continue
            reset_at = entry.get("last_error_reset_at")
            if isinstance(reset_at, (int, float)) and reset_at > time.time():
                continue
            if entry.get("last_status") not in {"quarantined", "invalid"} and fresh_token(entry.get("access_token")):
                return "hermes"
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return None


def load_config() -> dict:
    try:
        value = json.loads(CONFIG_FILE.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(value: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(value, indent=2))
    os.chmod(CONFIG_FILE, 0o600)


def key_is_valid(config: dict) -> bool:
    key = config.get("api_key")
    if not isinstance(key, str):
        return False
    try:
        http_json("/v1/models", api_key=key)
        return True
    except OperatorError:
        return False


def ensure_key(*, rotate: bool = False) -> None:
    config = load_config()
    if not rotate and key_is_valid(config):
        return
    old_id = config.get("key_id")
    if rotate and isinstance(old_id, int):
        try:
            http_json(f"/api/keys/{old_id}", method="DELETE")
        except OperatorError:
            pass
    created = http_json("/api/keys", method="POST", payload={"name": "Hermes autonomous skill"})["data"]
    save_config({"base_url": f"{ORIGIN}/v1", "api_key": created["secret"], "key_id": created["id"]})


def device_login() -> None:
    login = http_json("/api/auth/device-code", method="POST")
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_PENDING_FILE.write_text(json.dumps({"created_at": time.time(), **login}))
    emit(
        "authentication_required",
        verification_url=login.get("verificationUrl"),
        user_code=login.get("userCode"),
        login_id=login.get("loginId"),
        message="Open the verification URL, enter the code, approve access, then tell Hermes you are done.",
    )


def pending_login() -> dict | None:
    try:
        value = json.loads(AUTH_PENDING_FILE.read_text())
        if isinstance(value, dict) and time.time() - float(value.get("created_at", 0)) < 900:
            return value
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    AUTH_PENDING_FILE.unlink(missing_ok=True)
    return None


def emit_pending(login: dict) -> None:
    emit(
        "authentication_pending",
        verification_url=login.get("verificationUrl"),
        user_code=login.get("userCode"),
        message="Finish the browser approval using this link and code, then tell Hermes you are done.",
    )


def ready_result() -> None:
    current = account() or {}
    source = auth_source()
    ensure_key()
    AUTH_PENDING_FILE.unlink(missing_ok=True)
    emit(
        "ready",
        service_url=f"{ORIGIN}/v1",
        account_type=current.get("type"),
        plan=current.get("planType"),
        auth_source=source,
        credential_file=str(CONFIG_FILE),
        message="GPTLink is installed, authenticated, running, and configured for this skill.",
    )


def setup(*, update: bool) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    install_app(update=update)
    if auth_source() != "hermes":
        install_codex()
    start_server()
    if auth_source():
        ready_result()
    else:
        pending = pending_login()
        emit_pending(pending) if pending else device_login()


def complete_auth() -> None:
    start_server()
    if not auth_source():
        if not command_path("codex"):
            install_codex()
            stop_server()
            start_server()
        pending = pending_login()
        if pending:
            emit_pending(pending)
        else:
            device_login()
        return
    ready_result()


def status() -> None:
    current = account() if healthy() else None
    source = auth_source()
    emit(
        "ready" if healthy() and source and key_is_valid(load_config()) else "not_ready",
        installed=(APP_DIR / ".venv/bin/python").exists(),
        server_healthy=healthy(),
        authenticated=bool(source),
        auth_source=source,
        key_configured=key_is_valid(load_config()) if healthy() else False,
        plan=current.get("planType") if current else None,
    )


def log_tail(lines: int) -> str:
    try:
        return "\n".join(LOG_FILE.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return "No GPTLink log exists yet."


def main() -> None:
    parser = argparse.ArgumentParser(description="Install and manage GPTLink for Hermes")
    parser.add_argument("command", choices=["setup", "auth-complete", "ensure", "status", "restart", "update", "rotate-key", "logs"])
    args = parser.parse_args()
    try:
        if args.command == "setup":
            setup(update=False)
        elif args.command == "auth-complete":
            complete_auth()
        elif args.command == "ensure":
            if not (APP_DIR / ".venv/bin/python").exists():
                setup(update=False)
            else:
                start_server()
                complete_auth()
        elif args.command == "status":
            status()
        elif args.command == "restart":
            stop_server()
            start_server()
            status()
        elif args.command == "update":
            install_app(update=True)
            install_codex()
            stop_server()
            start_server()
            complete_auth()
        elif args.command == "rotate-key":
            start_server()
            ensure_key(rotate=True)
            emit("ready", message="The Hermes GPTLink API key was rotated and saved securely.")
        else:
            print(log_tail(100))
    except (OperatorError, OSError, KeyError, ValueError) as exc:
        emit("error", message=str(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
