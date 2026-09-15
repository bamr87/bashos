"""A tiny asyncio HTTP/1.1 server — the transport under the bashOS desktop.

bashOS ships no web framework: the terminal never needed one, and the desktop
front end has to work straight after `pip install bashos`. So the GUI rides on
asyncio and the standard library — request parsing, a path router, JSON, static
files, and server-sent events, in one readable file.

Deliberately small: one request per connection (no keep-alive, no pipelining,
no chunked request bodies), hard caps on every input, loopback by default.
Anything this cannot express does not belong in a local GUI transport.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import urllib.parse
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

MAX_LINE = 8192  # request line, or any single header
MAX_HEADERS = 64
MAX_BODY = 1 << 20  # 1 MiB — a GUI request is a command line, not an upload

STATUS_TEXT = {
    200: "OK",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    413: "Content Too Large",
    431: "Request Header Fields Too Large",
    500: "Internal Server Error",
}

# Sent on every response. The GUI loads nothing from anywhere but itself, so
# say so: a strict policy here is what keeps a local page that can run kernel
# commands from being driven by anything else.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; font-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
}


class HttpError(Exception):
    """Raised by a handler to answer with a status instead of a body."""

    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(message or STATUS_TEXT.get(status, "error"))
        self.status = status
        self.message = message or STATUS_TEXT.get(status, "error")


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: bytes
    params: dict[str, str] = field(default_factory=dict)

    def header(self, name: str, default: str = "") -> str:
        return self.headers.get(name.lower(), default)

    def json(self) -> Any:
        if not self.body:
            return {}
        try:
            return json.loads(self.body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HttpError(400, f"invalid JSON body: {exc}") from exc


@dataclass
class Response:
    body: bytes = b""
    status: int = 200
    content_type: str = "application/json; charset=utf-8"
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Stream:
    """A server-sent event response: an async iterator of (event, payload)."""

    source: Callable[[], AsyncIterator[tuple[str, Any]]]


Handler = Callable[[Request], Awaitable[Response | Stream]]


def json_response(payload: Any, status: int = 200) -> Response:
    return Response(json.dumps(payload).encode(), status=status)


def text_response(text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> Response:
    return Response(text.encode(), status=status, content_type=content_type)


def error_response(status: int, message: str) -> Response:
    return json_response({"error": message, "status": status}, status=status)


class Router:
    """Exact-path routing with `{name}` segment captures — no regex surprises."""

    def __init__(self) -> None:
        self._routes: list[tuple[str, tuple[str, ...], Handler]] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        self._routes.append((method.upper(), tuple(pattern.strip("/").split("/")), handler))

    def get(self, pattern: str) -> Callable[[Handler], Handler]:
        return self._register("GET", pattern)

    def post(self, pattern: str) -> Callable[[Handler], Handler]:
        return self._register("POST", pattern)

    def _register(self, method: str, pattern: str) -> Callable[[Handler], Handler]:
        def decorate(handler: Handler) -> Handler:
            self.add(method, pattern, handler)
            return handler

        return decorate

    def match(self, method: str, path: str) -> tuple[Handler, dict[str, str]]:
        parts = tuple(path.strip("/").split("/"))
        allowed = False
        for route_method, pattern, handler in self._routes:
            if len(pattern) != len(parts):
                continue
            params: dict[str, str] = {}
            for expected, actual in zip(pattern, parts, strict=True):
                if expected.startswith("{") and expected.endswith("}"):
                    params[expected[1:-1]] = urllib.parse.unquote(actual)
                elif expected != actual:
                    break
            else:
                if route_method == method:
                    return handler, params
                allowed = True
        raise HttpError(405 if allowed else 404)


class HttpServer:
    """Serves one router on a loopback socket until `close()`."""

    def __init__(
        self,
        router: Router,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        before: Callable[[Request], None] | None = None,
    ) -> None:
        self.router = router
        self.host = host
        self.port = port
        self._before = before  # host/origin/token guard, run before dispatch
        self._server: asyncio.AbstractServer | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    async def start(self) -> HttpServer:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        sockets = self._server.sockets or ()
        if sockets and self.port == 0:
            self.port = sockets[0].getsockname()[1]
        return self

    async def close(self) -> None:
        if self._server is None:
            return
        server, self._server = self._server, None
        server.close()
        with contextlib.suppress(Exception):
            await server.wait_closed()

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    # ------------------------------------------------------------ connection

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await _read_request(reader)
            result = await self._dispatch(request)
            if isinstance(result, Stream):
                await _write_stream(writer, result)
            else:
                await _write_response(writer, result)
        except HttpError as exc:
            with contextlib.suppress(Exception):
                await _write_response(writer, error_response(exc.status, exc.message))
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass  # the page navigated away mid-request; nothing to report
        except Exception as exc:  # a handler bug must not take the server down
            with contextlib.suppress(Exception):
                await _write_response(writer, error_response(500, str(exc)))
        finally:
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _dispatch(self, request: Request) -> Response | Stream:
        if self._before is not None:
            self._before(request)
        handler, params = self.router.match(request.method, request.path)
        bound = Request(
            method=request.method,
            path=request.path,
            query=request.query,
            headers=request.headers,
            body=request.body,
            params=params,
        )
        return await handler(bound)


async def _read_request(reader: asyncio.StreamReader) -> Request:
    try:
        line = await reader.readuntil(b"\r\n")
    except asyncio.LimitOverrunError as exc:
        raise HttpError(431, "request line too long") from exc
    if len(line) > MAX_LINE:
        raise HttpError(431, "request line too long")
    try:
        method, target, _version = line.decode("latin-1").split()
    except ValueError as exc:
        raise HttpError(400, "malformed request line") from exc

    headers: dict[str, str] = {}
    for _ in range(MAX_HEADERS + 1):
        raw = await reader.readuntil(b"\r\n")
        if raw in (b"\r\n", b"\n"):
            break
        if len(raw) > MAX_LINE:
            raise HttpError(431, "header too long")
        name, _, value = raw.decode("latin-1").partition(":")
        headers[name.strip().lower()] = value.strip()
    else:
        raise HttpError(431, "too many headers")

    length = headers.get("content-length", "0")
    try:
        size = int(length)
    except ValueError as exc:
        raise HttpError(400, "invalid Content-Length") from exc
    if size > MAX_BODY:
        raise HttpError(413, "body too large")
    body = await reader.readexactly(size) if size > 0 else b""

    path, _, raw_query = target.partition("?")
    query = {k: v[-1] for k, v in urllib.parse.parse_qs(raw_query, keep_blank_values=True).items()}
    return Request(
        method=method.upper(),
        path=urllib.parse.unquote(path) or "/",
        query=query,
        headers=headers,
        body=body,
    )


def _head(status: int, content_type: str, extra: dict[str, str]) -> bytes:
    reason = STATUS_TEXT.get(status, "OK")
    lines = [f"HTTP/1.1 {status} {reason}", f"Content-Type: {content_type}"]
    lines += [f"{name}: {value}" for name, value in {**SECURITY_HEADERS, **extra}.items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


async def _write_response(writer: asyncio.StreamWriter, response: Response) -> None:
    extra = {
        "Content-Length": str(len(response.body)),
        "Connection": "close",
        "Cache-Control": "no-store",
        **response.headers,
    }
    writer.write(_head(response.status, response.content_type, extra))
    if response.body:
        writer.write(response.body)
    await writer.drain()


async def _write_stream(writer: asyncio.StreamWriter, stream: Stream) -> None:
    writer.write(
        _head(
            200,
            "text/event-stream; charset=utf-8",
            {
                "Cache-Control": "no-store",
                "Connection": "close",
                "X-Accel-Buffering": "no",  # no proxy should buffer a live run
            },
        )
    )
    await writer.drain()
    async for event, payload in stream.source():
        # json.dumps escapes newlines, so every event is exactly one data line
        chunk = f"event: {event}\ndata: {json.dumps(payload)}\n\n"
        writer.write(chunk.encode())
        await writer.drain()
