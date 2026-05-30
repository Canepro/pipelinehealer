"""Codex App Server model-runtime adapter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from typing import Any
from urllib.parse import urlparse


class CodexAppServerAgent:
    """Minimal text agent backed by the Codex App Server JSON-RPC protocol."""

    def __init__(self, *, settings: Any, instructions: str) -> None:
        self._settings = settings
        self._instructions = instructions
        self._last_call_used_fallback = False

    @property
    def last_call_used_fallback(self) -> bool:
        return self._last_call_used_fallback

    async def run(self, prompt: str) -> str:
        transport = str(getattr(self._settings, "codex_app_server_transport", "stdio") or "stdio")
        if transport == "websocket":
            return await self._run_websocket(prompt)
        return await self._run_stdio(prompt)

    def _model(self) -> str:
        return str(getattr(self._settings, "codex_app_server_model", "") or "").strip() or "gpt-5.4"

    def _timeout_seconds(self) -> float:
        timeout_ms = int(getattr(self._settings, "codex_app_server_turn_timeout_ms", 120000) or 120000)
        return max(1.0, timeout_ms / 1000.0)

    def _command(self) -> list[str]:
        raw = str(getattr(self._settings, "codex_app_server_command", "") or "").strip()
        return raw.split() or ["codex", "app-server"]

    async def _run_stdio(self, prompt: str) -> str:
        command = self._command()
        process = await asyncio.create_subprocess_exec(
            command[0],
            *command[1:],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def write_line(line: str) -> None:
            if process.stdin is None:
                raise RuntimeError("Codex App Server stdin is unavailable")
            process.stdin.write((line.rstrip("\n") + "\n").encode("utf-8"))
            await process.stdin.drain()

        async def read_line() -> str:
            if process.stdout is None:
                raise RuntimeError("Codex App Server stdout is unavailable")
            raw = await process.stdout.readline()
            if not raw:
                stderr = b""
                if process.stderr is not None:
                    stderr = await process.stderr.read()
                raise RuntimeError(
                    "Codex App Server exited before completing a turn"
                    + (f": {stderr.decode('utf-8', errors='replace').strip()}" if stderr else "")
                )
            return raw.decode("utf-8", errors="replace")

        try:
            return await _CodexJsonRpcSession(
                write_line=write_line,
                read_line=read_line,
                model=self._model(),
                instructions=self._instructions,
                timeout_seconds=self._timeout_seconds(),
            ).run(prompt)
        finally:
            with suppress(Exception):
                if process.stdin is not None:
                    process.stdin.close()
                    await process.stdin.wait_closed()
            with suppress(Exception):
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)

    async def _run_websocket(self, prompt: str) -> str:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "Codex App Server websocket transport requires the websockets package"
            ) from exc

        ws_url = str(getattr(self._settings, "codex_app_server_ws_url", "") or "").strip()
        parsed = urlparse(ws_url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
            raise RuntimeError("CODEX_APP_SERVER_WS_URL must be a ws:// or wss:// URL")

        token = self._websocket_token()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        async with websockets.connect(ws_url, extra_headers=headers) as websocket:
            async def write_line(line: str) -> None:
                await websocket.send(line.rstrip("\n"))

            async def read_line() -> str:
                return str(await websocket.recv())

            return await _CodexJsonRpcSession(
                write_line=write_line,
                read_line=read_line,
                model=self._model(),
                instructions=self._instructions,
                timeout_seconds=self._timeout_seconds(),
            ).run(prompt)

    def _websocket_token(self) -> str:
        token = str(getattr(self._settings, "codex_app_server_ws_bearer_token", "") or "").strip()
        if token:
            return token
        for attr in ("codex_app_server_ws_token_file", "codex_app_server_ws_shared_secret_file"):
            path = str(getattr(self._settings, attr, "") or "").strip()
            if path:
                with open(path, encoding="utf-8") as handle:
                    return handle.read().strip()
        return ""


class _CodexJsonRpcSession:
    def __init__(
        self,
        *,
        write_line: Callable[[str], Any],
        read_line: Callable[[], Any],
        model: str,
        instructions: str,
        timeout_seconds: float,
    ) -> None:
        self._write_line = write_line
        self._read_line = read_line
        self._model = model
        self._instructions = instructions
        self._timeout_seconds = timeout_seconds
        self._next_id = 1
        self._notifications: list[Any] = []

    async def run(self, prompt: str) -> str:
        await self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "pipelinehealer",
                    "title": "PipelineHealer",
                    "version": "1.0.0",
                },
                "capabilities": {
                    "optOutNotificationMethods": [
                        "item/agentMessage/delta",
                        "command/exec/outputDelta",
                        "process/outputDelta",
                    ],
                },
            },
        )
        await self._notify("initialized", {})
        thread_result = await self._request(
            "thread/start",
            {"model": self._model, "ephemeral": True, "serviceName": "pipelinehealer"},
        )
        thread_id = _extract_thread_id(thread_result)
        if not thread_id:
            raise RuntimeError("Codex App Server thread/start did not return a thread id")

        await self._request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "developerInstructions": self._instructions,
                "approvalPolicy": "never",
                "sandboxPolicy": {"type": "readOnly", "networkAccess": False},
                "outputSchema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        )
        await asyncio.wait_for(self._wait_for_turn_completed(), timeout=self._timeout_seconds)
        text = _extract_text({"notifications": self._notifications})
        if not text:
            raise RuntimeError("Codex App Server turn completed without text output")
        return text

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write_line(json.dumps({"method": method, "params": params}))

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        await self._write_line(json.dumps({"id": request_id, "method": method, "params": params}))
        while True:
            message = await self._read_json_line()
            if message.get("id") == request_id:
                if message.get("error"):
                    error = message["error"]
                    if isinstance(error, dict):
                        raise RuntimeError(str(error.get("message") or error))
                    raise RuntimeError(str(error))
                return message.get("result")
            self._notifications.append(message)

    async def _wait_for_turn_completed(self) -> None:
        while True:
            message = await self._read_json_line()
            self._notifications.append(message)
            if message.get("method") == "turn/completed":
                return

    async def _read_json_line(self) -> dict[str, Any]:
        while True:
            raw = await self._read_line()
            text = raw.strip()
            if not text:
                continue
            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                return message


def _extract_thread_id(payload: Any) -> str:
    if isinstance(payload, dict):
        thread = payload.get("thread")
        if isinstance(thread, dict):
            value = thread.get("id")
            return str(value) if value else ""
    return ""


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, list):
        for item in payload:
            text = _extract_text(item)
            if text:
                return text
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in (
        "text",
        "structuredOutput",
        "structured_output",
        "structuredContent",
        "structured_content",
        "output",
        "finalOutput",
        "final_output",
        "content",
    ):
        value = payload.get(key)
        if key in {
            "structuredOutput",
            "structured_output",
            "structuredContent",
            "structured_content",
        } and isinstance(value, dict) and isinstance(value.get("text"), str):
            return value["text"].strip()
        text = _extract_text(value)
        if text:
            return text
    for key in ("params", "turn", "items", "notifications"):
        text = _extract_text(payload.get(key))
        if text:
            return text
    return ""
