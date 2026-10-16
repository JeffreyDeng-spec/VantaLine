"""ASGI presentation adapter inside compression and outside route validation.

Only text form fields are buffered; uploaded files pass through incrementally and
unchanged. Model references are resolved before existing domain authorization,
fingerprinting, model pinning and PLC lease validation.
"""
import json
from urllib.parse import parse_qsl, urlencode
from python_multipart.multipart import MultipartParser, parse_options_header
from .presentation import Presentation, internal_route


class FormStream:
    def __init__(self, boundary: bytes, presentation: Presentation):
        self.boundary, self.presentation = boundary, presentation
        self.pending = []
        self.done = False
        self.parser = MultipartParser(boundary, {
            "on_part_begin": self.begin, "on_header_field": self.header_field,
            "on_header_value": self.header_value, "on_header_end": self.header_end,
            "on_headers_finished": self.headers_end, "on_part_data": self.data,
            "on_part_end": self.end, "on_end": self.finish,
        })

    def begin(self):
        self.headers, self.header_name, self.header_body = [], b"", b""
        self.buffer = bytearray()
        self.pending.append(b"--" + self.boundary + b"\r\n")

    def header_field(self, data, start, end):
        if len(self.header_name) + end - start > 65536:
            raise ValueError("Invalid form")
        self.header_name += data[start:end]

    def header_value(self, data, start, end):
        if len(self.header_body) + end - start > 65536:
            raise ValueError("Invalid form")
        self.header_body += data[start:end]

    def header_end(self):
        if sum(len(k) + len(v) for k, v in self.headers) + len(self.header_name) + len(self.header_body) > 65536:
            raise ValueError("Invalid form")
        self.headers.append((self.header_name, self.header_body))
        self.header_name, self.header_body = b"", b""

    def headers_end(self):
        disposition = next((v for k, v in self.headers if k.lower() == b"content-disposition"), b"")
        _, options = parse_options_header(disposition)
        self.file = b"filename" in options
        self.name = options.get(b"name", b"").decode("utf-8")
        self.pending.append(b"".join(k + b": " + v + b"\r\n" for k, v in self.headers) + b"\r\n")

    def data(self, data, start, end):
        if self.file:
            self.pending.append(data[start:end])
        else:
            if len(self.buffer) + end - start > 65536:
                raise ValueError("Form field too large")
            self.buffer.extend(data[start:end])

    def end(self):
        if not self.file:
            text = self.presentation.incoming(self.buffer.decode("utf-8"), self.name)
            self.pending.append(text.encode("utf-8"))
        self.pending.append(b"\r\n")

    def finish(self):
        self.done = True
        self.pending.append(b"--" + self.boundary + b"--\r\n")


class ModelPrivacyMiddleware:
    def __init__(self, app, presentation: Presentation):
        self.app, self.presentation = app, presentation

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        original_path = scope["path"]
        if not original_path.startswith(("/api/", "/outputs/")):
            return await self.app(scope, receive, send)
        user = scope.get("state", {}).get("user") or {}
        admin = user.get("role") == "admin"
        # Registry/auth/worker transports retain their exact original contracts.
        # Worker transfer tokens authorize machine traffic independently of users.
        transfer = original_path.startswith("/api/training/runpod/")
        auth_route = original_path.startswith("/api/auth/")
        if original_path.startswith(("/api/admin/", "/api/ai/config", "/api/agent/config")) or original_path == "/api/version" or transfer:
            return await self.app(scope, receive, send)
        presentation = self.presentation
        try:
            scope = dict(scope)
            scope["path"] = presentation.path(original_path, incoming=True)
            scope["raw_path"] = scope["path"].encode("utf-8")
            query = parse_qsl(scope.get("query_string", b"").decode(), keep_blank_values=True)
            scope["query_string"] = urlencode([(key, presentation.incoming(value, key)) for key, value in query]).encode()
        except ValueError:
            return await self.error(send)
        headers = dict(scope["headers"])
        content_type, options = parse_options_header(headers.get(b"content-type", b""))
        upstream = receive
        if content_type == b"application/json" and not auth_route:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 32 * 1024 * 1024:
                    return await self.error(send, 413)
                if not message.get("more_body"):
                    break
            try:
                encoded = json.dumps(presentation.incoming(json.loads(body or b"{}")), ensure_ascii=False).encode()
            except (ValueError, UnicodeError):
                return await self.error(send)
            delivered = False
            async def json_receive():
                nonlocal delivered
                if delivered:
                    return await upstream()
                delivered = True
                return {"type": "http.request", "body": encoded, "more_body": False}
            receive = json_receive
        elif content_type == b"multipart/form-data" and b"boundary" in options:
            form = FormStream(options[b"boundary"], presentation)
            async def form_receive():
                while not form.pending and not form.done:
                    message = await upstream()
                    if message["type"] != "http.request":
                        return message
                    form.parser.write(message.get("body", b""))
                    if not message.get("more_body"):
                        form.parser.finalize()
                        if not form.done:
                            raise ValueError("Incomplete form")
                data = b"".join(form.pending)
                form.pending.clear()
                return {"type": "http.request", "body": data, "more_body": not form.done}
            receive = form_receive
        if receive is not upstream:
            scope["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"content-length"]

        start, pieces = None, []
        event_stream = False
        event_buffer = b""
        async def projected_send(message):
            nonlocal start, event_stream, event_buffer
            if message["type"] == "http.response.start":
                response_headers = dict(message["headers"])
                event_stream = b"text/event-stream" in response_headers.get(b"content-type", b"")
                if event_stream:
                    message["headers"] = [(k,v) for k,v in message["headers"] if k.lower() not in {b"content-length", b"cache-control"}]
                    message["headers"].append((b"cache-control", b"private, no-store"))
                if b"application/json" in response_headers.get(b"content-type", b""):
                    start = message
                    return
            if start is None:
                if event_stream and message["type"] == "http.response.body":
                    event_buffer += message.get("body", b"")
                    lines = event_buffer.splitlines(keepends=True)
                    event_buffer = b""
                    if message.get("more_body") and lines and not lines[-1].endswith((b"\n", b"\r")):
                        event_buffer = lines.pop()
                    output = []
                    for line in lines:
                        if line.startswith(b"data:"):
                            try:
                                data = json.loads(line[5:])
                                data = presentation.outgoing(data, admin=admin, plc=scope["path"].startswith("/api/plc/"))
                                line = b"data: " + json.dumps(data, ensure_ascii=False).encode() + b"\n"
                            except (ValueError, UnicodeError):
                                line = b'data: {"status":"unavailable"}\n'
                        output.append(line)
                    message = {**message, "body": b"".join(output)}
                return await send(message)
            if message["type"] == "http.response.body":
                pieces.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                data = json.loads(b"".join(pieces))
                plc = scope["path"].startswith("/api/plc/")
                response_admin = admin or (auth_route and isinstance(data, dict) and (data.get("user") or {}).get("role") == "admin")
                if not response_admin and start["status"] >= 500:
                    data = {"detail": "服务暂时不可用，请稍后检查或联系管理员。", "code": "service_unavailable"}
                data = presentation.outgoing(data, admin=response_admin, plc=plc)
                encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
                start["headers"] = [(k, v) for k, v in start["headers"] if k.lower() not in {b"content-length", b"etag", b"cache-control"}]
                start["headers"] += [(b"content-length", str(len(encoded)).encode()), (b"cache-control", b"private, no-store"), (b"vary", b"Cookie")]
                await send(start)
                await send({"type": "http.response.body", "body": encoded})
        await self.app(scope, receive, projected_send)

    @staticmethod
    async def error(send, status=422):
        body = b'{"detail":"Invalid request"}'
        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})
