"""Codex App Server model-runtime adapter."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlparse


@dataclass(frozen=True)
class CodexTurnOptions:
    """Per-turn execution policy for a Codex App Server session."""

    cwd: str | None = None
    sandbox_mode: str = "readOnly"
    network_access: bool = False
    timeout_seconds: float | None = None
    text_output_schema: bool = True
    require_text: bool = True
    sanitize_env: bool = False


# Environment kept for sanitized (workspace-write) Codex subprocesses: shell
# basics only. Backend and provider secrets (GitHub tokens, Azure keys, DSNs,
# admin keys, OPENAI_API_KEY) are deliberately dropped so an agent turn over
# untrusted repository content cannot read and exfiltrate them; the codex CLI
# must authenticate through its own credential store (codex login) under HOME.
_SANITIZED_ENV_KEYS = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "TERM",
    "COLUMNS",
    "LINES",
    "OPENAI_BASE_URL",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
}
_SANITIZED_ENV_PREFIXES = ("LC_", "XDG_", "CODEX_HOME")


def sanitized_agent_env() -> dict[str, str]:
    """Return a minimal subprocess environment for workspace-write agent turns."""
    return {
        key: value
        for key, value in os.environ.items()
        if key in _SANITIZED_ENV_KEYS or key.startswith(_SANITIZED_ENV_PREFIXES)
    }


def is_loopback_websocket_host(hostname: str) -> bool:
    """Return whether a WebSocket hostname is constrained to the local host."""
    host = hostname.strip().lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class CodexAppServerAgent:
    """Minimal text agent backed by the Codex App Server JSON-RPC protocol."""

    def __init__(self, *, settings: Any, instructions: str) -> None:
        self._settings = settings
        self._instructions = instructions
        self._last_call_used_fallback = False

    @property
    def last_call_used_fallback(self) -> bool:
        return self._last_call_used_fallback

    async def run(self, prompt: str, options: CodexTurnOptions | None = None) -> str:
        options = options or CodexTurnOptions()
        transport = str(getattr(self._settings, "codex_app_server_transport", "stdio") or "stdio")
        if transport == "websocket":
            return await self._run_websocket(prompt, options)
        return await self._run_stdio(prompt, options)

    async def run_agentic(
        self,
        prompt: str,
        *,
        cwd: str,
        timeout_seconds: float | None = None,
    ) -> str:
        """Run one workspace-write turn that may edit files under cwd."""
        return await self.run(
            prompt,
            CodexTurnOptions(
                cwd=cwd,
                sandbox_mode="workspaceWrite",
                network_access=False,
                timeout_seconds=timeout_seconds,
                text_output_schema=False,
                require_text=False,
                sanitize_env=True,
            ),
        )

    def _model(self) -> str:
        return str(getattr(self._settings, "codex_app_server_model", "") or "").strip() or "gpt-5.4"

    def _timeout_seconds(self) -> float:
        timeout_ms = int(getattr(self._settings, "codex_app_server_turn_timeout_ms", 120000) or 120000)
        return max(1.0, timeout_ms / 1000.0)

    def _command(self) -> list[str]:
        raw = str(getattr(self._settings, "codex_app_server_command", "") or "").strip()
        return raw.split() or ["codex", "app-server"]

    async def _run_stdio(self, prompt: str, options: CodexTurnOptions | None = None) -> str:
        options = options or CodexTurnOptions()
        command = self._command()
        process = await asyncio.create_subprocess_exec(
            command[0],
            *command[1:],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=sanitized_agent_env() if options.sanitize_env else None,
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
                timeout_seconds=options.timeout_seconds or self._timeout_seconds(),
                options=options,
            ).run(prompt)
        finally:
            with suppress(Exception):
                if process.stdin is not None:
                    process.stdin.close()
                    await process.stdin.wait_closed()
            with suppress(Exception):
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)

    async def _run_websocket(self, prompt: str, options: CodexTurnOptions | None = None) -> str:
        options = options or CodexTurnOptions()
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
        allow_remote = bool(getattr(self._settings, "codex_app_server_ws_allow_remote", False))
        if not allow_remote and not is_loopback_websocket_host(parsed.hostname):
            raise RuntimeError(
                "CODEX_APP_SERVER_WS_ALLOW_REMOTE must be true for non-loopback "
                "Codex App Server WebSocket URLs"
            )

        token = self._websocket_token()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        async with websockets.connect(ws_url, additional_headers=headers) as websocket:
            async def write_line(line: str) -> None:
                await websocket.send(line.rstrip("\n"))

            async def read_line() -> str:
                return str(await websocket.recv())

            return await _CodexJsonRpcSession(
                write_line=write_line,
                read_line=read_line,
                model=self._model(),
                instructions=self._instructions,
                timeout_seconds=options.timeout_seconds or self._timeout_seconds(),
                options=options,
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
        options: CodexTurnOptions | None = None,
    ) -> None:
        self._write_line = write_line
        self._read_line = read_line
        self._model = model
        self._instructions = instructions
        self._timeout_seconds = timeout_seconds
        self._options = options or CodexTurnOptions()
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
        thread_params: dict[str, Any] = {
            "model": self._model,
            "ephemeral": True,
            "serviceName": "pipelinehealer",
        }
        if self._options.cwd:
            thread_params["cwd"] = self._options.cwd
        thread_result = await self._request("thread/start", thread_params)
        thread_id = _extract_thread_id(thread_result)
        if not thread_id:
            raise RuntimeError("Codex App Server thread/start did not return a thread id")

        turn_params: dict[str, Any] = {
            "threadId": thread_id,
            "input": [{"type": "text", "text": prompt}],
            "developerInstructions": self._instructions,
            "approvalPolicy": "never",
            "sandboxPolicy": {
                "type": self._options.sandbox_mode,
                "networkAccess": self._options.network_access,
            },
        }
        if self._options.cwd:
            turn_params["cwd"] = self._options.cwd
        if self._options.text_output_schema:
            turn_params["outputSchema"] = {
                "type": "object",
                "additionalProperties": False,
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            }
        await self._request("turn/start", turn_params)
        await asyncio.wait_for(self._wait_for_turn_completed(), timeout=self._timeout_seconds)
        text = _extract_text({"notifications": self._notifications})
        if not text and self._options.require_text:
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
    agent_message_text = _extract_agent_message_text(payload)
    if agent_message_text:
        return agent_message_text

    return _extract_text_generic(payload)


def _decode_text_envelope(value: str) -> str:
    text = value.strip()
    if not text.startswith("{"):
        return text
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text
    if (
        isinstance(parsed, dict)
        and set(parsed) == {"text"}
        and isinstance(parsed.get("text"), str)
    ):
        parsed_text = cast(str, parsed["text"])
        return parsed_text.strip()
    return text


def _extract_agent_message_text(payload: Any) -> str:
    if isinstance(payload, list):
        for item in payload:
            text = _extract_agent_message_text(item)
            if text:
                return text
        return ""
    if not isinstance(payload, dict):
        return ""

    item = payload.get("item")
    if isinstance(item, dict) and item.get("type") == "agentMessage":
        raw_text = item.get("text")
        if isinstance(raw_text, str) and raw_text.strip():
            return _decode_text_envelope(raw_text)

    for key in ("params", "turn", "items", "notifications"):
        text = _extract_agent_message_text(payload.get(key))
        if text:
            return text
    return ""


def _extract_text_generic(payload: Any) -> str:
    if isinstance(payload, str):
        return _decode_text_envelope(payload)
    if isinstance(payload, list):
        for item in payload:
            text = _extract_text_generic(item)
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
        } and isinstance(value, dict):
            structured_text = value.get("text")
            if isinstance(structured_text, str):
                return structured_text.strip()
        text = _extract_text_generic(value)
        if text:
            return text
    for key in ("params", "turn", "items", "notifications"):
        text = _extract_text_generic(payload.get(key))
        if text:
            return text
    return ""
