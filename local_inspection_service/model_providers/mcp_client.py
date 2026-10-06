"""Optional stdio MCP client; process state belongs to each client instance."""
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any
import json
import subprocess
import sys
import threading
import time


class McpAdmissionClosed(RuntimeError):
    """A new operation was rejected before any provider transport or fallback."""


class LocalAiMcpClient:
    def __init__(self, *, root: Callable[[], Path], error: Callable[[], type[Exception]],
                 runtime: Callable[[], str]) -> None:
        self.root, self.error, self.runtime = root, error, runtime
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.RLock()
        self.next_id = 1
        self._condition = threading.Condition()
        self._local = threading.local()
        self._active = 0
        self._closing = False
        self._retired: list[subprocess.Popen[str]] = []

    @contextmanager
    def admission(self):
        depth = getattr(self._local, 'depth', 0)
        with self._condition:
            if not depth:
                if self._closing:
                    raise McpAdmissionClosed("AI MCP runtime is closing")
                self._active += 1
            self._local.depth = depth + 1
        try:
            yield
        finally:
            with self._condition:
                self._local.depth = depth
                if not depth:
                    self._active -= 1
                    self._condition.notify_all()

    def shutdown(self, timeout: float) -> bool:
        """Reject new operations and drain before terminating/reaping transports.

        Timeout leaves all active work untouched. The caller must retain this
        owner and retry draining later; no cancellation or fallback is induced.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            self._closing = True
            if getattr(self._local, 'depth', 0):
                return False
            while self._active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
        if not self.lock.acquire(timeout=max(0.0, deadline - time.monotonic())):
            return False
        try:
            processes = list(self._retired)
            if self.process is not None and not any(p is self.process for p in processes):
                processes.append(self.process)
            for process in processes:
                if process.poll() is None and not any(p is process for p in self._retired):
                    process.terminate()
                    self._retired.append(process)
                try:
                    process.wait(timeout=max(0.0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    return False
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()
                self._retired = [p for p in self._retired if p is not process]
                if self.process is process:
                    self.process = None
            return True
        finally:
            self.lock.release()

    def close(self) -> None:
        with self.lock:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                if not any(p is self.process for p in self._retired):
                    self._retired.append(self.process)
            self.process = None

    def ensure_started(self) -> None:
        with self.admission(), self.lock:
            if self.process and self.process.poll() is None:
                return
            previous = self.process
            self.process = subprocess.Popen(
                [sys.executable, "-m", "local_inspection_service.ai_mcp_server"],
                cwd=str(self.root()),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            if previous is not None:
                self._retired.append(previous)
            self.request("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "local-inspection-service", "version": "0.1.0"}})

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.admission(), self.lock:
            if not self.process or not self.process.stdin or not self.process.stdout:
                raise self.error()("AI MCP client process is not started")
            message_id = self.next_id
            self.next_id += 1
            message = {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params or {}}
            self.process.stdin.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
            if not line:
                raise self.error()("AI MCP server closed stdout")
            response = json.loads(line)
            if not isinstance(response, dict):
                raise self.error()("AI MCP server returned non-object response")
            if response.get("error"):
                error = response["error"] if isinstance(response["error"], dict) else {}
                raise self.error()(str(error.get("message") or "AI MCP server error"))
            result = response.get("result")
            if not isinstance(result, dict):
                raise self.error()("AI MCP response result was not an object")
            return result

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        with self.admission():
            with self.lock:
                self.ensure_started()
                result = self.request("tools/call", {"name": tool_name, "arguments": arguments})
            content = result.get("content") if isinstance(result.get("content"), list) else []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parsed = json.loads(str(item.get("text") or "{}"))
                    if isinstance(parsed, dict):
                        parsed.setdefault("mcp_transport", "stdio")
                        parsed.setdefault("mcp_runtime", self.runtime())
                        return parsed
            raise self.error()("AI MCP tool response had no JSON text content")
