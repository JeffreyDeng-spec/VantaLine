import json
import os
import sys
import traceback
from typing import Any


os.environ["INSPECTION_AI_MCP_SERVER_MODE"] = "1"

from local_inspection_service.runtime.default_application import default_application  # noqa: E402

tool_definitions = default_application.values.AI_MCP_TOOL_DEFINITIONS
tool_handlers = default_application.inspection.AI_MCP_TOOL_HANDLERS


def json_schema_for_tool(tool_name: str) -> dict[str, Any]:
    definition = tool_definitions.get(tool_name, {})
    return {
        "type": "object",
        "description": definition.get("description", tool_name),
        "additionalProperties": True,
    }


def tool_list() -> list[dict[str, Any]]:
    tools = []
    for tool_name, definition in tool_definitions.items():
        tools.append(
            {
                "name": tool_name,
                "description": str(definition.get("description") or tool_name),
                "inputSchema": json_schema_for_tool(tool_name),
            }
        )
    return tools


def tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            }
        ]
    }


def error_response(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = str(message.get("method") or "")
    message_id = message.get("id")
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    if not message_id and method.startswith("notifications/"):
        return None
    try:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "assembly-line-ai-inspection",
                        "version": "0.1.0",
                    },
                    "capabilities": {
                        "tools": {},
                    },
                },
            }
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {"tools": tool_list()},
            }
        if method == "tools/call":
            tool_name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            handler = tool_handlers.get(tool_name)
            if handler is None:
                return error_response(message_id, -32602, f"Unknown tool: {tool_name}")
            result = handler(arguments)
            if not isinstance(result, dict):
                return error_response(message_id, -32603, f"Tool returned non-object result: {tool_name}")
            result.setdefault("tool", tool_name)
            return {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": tool_result(result),
            }
        return error_response(message_id, -32601, f"Unsupported MCP method: {method}")
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        return error_response(message_id, -32603, str(exc))


def main() -> None:
    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
            if not isinstance(message, dict):
                raise ValueError("MCP message must be a JSON object")
            response = handle_request(message)
        except Exception as exc:
            response = error_response(None, -32700, str(exc))
        if response is None:
            continue
        sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
