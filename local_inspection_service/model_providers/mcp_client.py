"""Optional stdio MCP client; process state belongs to each client instance."""
from collections.abc import Callable
from pathlib import Path
from typing import Any
import json
import subprocess
import sys
import threading


class LocalAiMcpClient:
    def __init__(self, *, root: Callable[[], Path], error: Callable[[], type[Exception]],
                 runtime: Callable[[], str]) -> None:
        self.root, self.error, self.runtime = root, error, runtime
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.RLock()
        self.next_id = 1

    def close(self) -> None:
        with self.lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
            self.process = None

    def ensure_started(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.process = subprocess.Popen(
            [sys.executable, "-m", "local_inspection_service.ai_mcp_server"],
            cwd=str(self.root()),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.request("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "local-inspection-service", "version": "0.1.0"}})

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
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
