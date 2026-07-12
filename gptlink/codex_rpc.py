from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable
from typing import Any

logger = logging.getLogger(__name__)


class CodexRpcError(RuntimeError):
    pass


class CodexAppServer:
    def __init__(self) -> None:
        self.process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self.initialize_result: dict[str, Any] | None = None

    async def start(self) -> None:
        if self.process and self.process.returncode is None:
            return
        self.process = await asyncio.create_subprocess_exec(
            "codex",
            "app-server",
            "--listen",
            "stdio://",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())
        self.initialize_result = await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "gptlink",
                    "title": "GPTLink Image Gateway",
                    "version": "0.4.0",
                }
            },
        )
        await self.notify("initialized", {})

    async def stop(self) -> None:
        if not self.process:
            return
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        for task in (self._reader_task, self._stderr_task):
            if task and not task.done():
                task.cancel()
        self.process = None

    async def request(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 30
    ) -> dict[str, Any]:
        if not self.process or not self.process.stdin:
            raise CodexRpcError("Codex app-server is not running")
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self._send({"method": method, "id": request_id, "params": params or {}})
        try:
            envelope = await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)
        if "error" in envelope:
            error = envelope["error"]
            message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            raise CodexRpcError(f"Codex {method} failed: {message}")
        result = envelope.get("result", {})
        return result if isinstance(result, dict) else {"value": result}

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self._send({"method": method, "params": params or {}})

    async def _send(self, payload: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise CodexRpcError("Codex app-server is not running")
        encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            self.process.stdin.write(encoded)
            await self.process.stdin.drain()

    async def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        while line := await self.process.stdout.readline():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Ignored non-JSON Codex output")
                continue
            request_id = message.get("id")
            if isinstance(request_id, int) and request_id in self._pending:
                future = self._pending[request_id]
                if not future.done():
                    future.set_result(message)

    async def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        while line := await self.process.stderr.readline():
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                logger.debug("Codex: %s", text)


async def tolerate_codex_failure(operation: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    try:
        return await operation
    except (CodexRpcError, TimeoutError, OSError) as exc:
        return {"error": str(exc)}
