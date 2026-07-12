from __future__ import annotations

import threading
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from gptlink.config import settings


def open_dashboard() -> None:
    webbrowser.open(f"http://{settings.host}:{settings.port}")


def is_already_running() -> bool:
    try:
        with urllib.request.urlopen(
            f"http://{settings.host}:{settings.port}/health", timeout=1
        ) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


if __name__ == "__main__":
    if is_already_running():
        open_dashboard()
        raise SystemExit(0)
    threading.Timer(1.25, open_dashboard).start()
    uvicorn.run("gptlink.main:app", host=settings.host, port=settings.port, reload=False)
