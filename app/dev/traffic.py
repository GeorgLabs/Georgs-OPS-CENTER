"""Dev tool: records every request your API handles, for the Traffic panel in the UI.

Pure ASGI middleware (no BaseHTTPMiddleware) so it can watch bodies without buffering whole
responses. Secrets are masked BEFORE anything is stored - logs and panels are a classic leak.
"""

import re
import threading
import time
from collections import deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send

BODY_LIMIT = 2000
_SKIP_PREFIXES = ("/_dev", "/static", "/docs", "/openapi.json")

_lock = threading.Lock()
_items: deque[dict] = deque(maxlen=300)
_seq = 0

_MASKS = [
    (re.compile(r'("(?:password|access_token|api_key)"\s*:\s*")[^"]*'), r"\1***"),
    (re.compile(r"((?:password|client_secret)=)[^&\s]*"), r"\1***"),
]


def _mask(text: str) -> str:
    for pattern, repl in _MASKS:
        text = pattern.sub(repl, text)
    return text


def _readable(raw: bytes, content_type: str) -> str:
    if not raw:
        return ""
    if not any(t in content_type for t in ("json", "text", "x-www-form-urlencoded")):
        return f"<{content_type or 'binary'}, {len(raw)}+ bytes>"
    return _mask(raw.decode("utf-8", errors="replace"))


def snapshot(after: int) -> dict:
    with _lock:
        return {"seq": _seq, "items": [i for i in _items if i["seq"] > after]}


class TrafficMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(_SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return
        request_headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        if request_headers.get("x-mission-probe"):  # Mission Control's own requests: not interesting
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        request_body = bytearray()
        response_body = bytearray()
        status = 0
        response_type = ""

        async def recv() -> Message:
            message = await receive()
            if message["type"] == "http.request" and len(request_body) < BODY_LIMIT:
                request_body.extend(message.get("body", b"")[: BODY_LIMIT - len(request_body)])
            return message

        async def snd(message: Message) -> None:
            nonlocal status, response_type
            if message["type"] == "http.response.start":
                status = message["status"]
                for k, v in message.get("headers", []):
                    if k.lower() == b"content-type":
                        response_type = v.decode("latin-1")
            elif message["type"] == "http.response.body" and len(response_body) < BODY_LIMIT:
                response_body.extend(message.get("body", b"")[: BODY_LIMIT - len(response_body)])
            await send(message)

        try:
            await self.app(scope, recv, snd)
        finally:
            query = scope.get("query_string", b"").decode("latin-1")
            entry = {
                "time": time.strftime("%H:%M:%S"),
                "method": scope["method"],
                "path": scope["path"] + (f"?{query}" if query else ""),
                "status": status or 500,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "request": _readable(bytes(request_body), request_headers.get("content-type", "")),
                "response": _readable(bytes(response_body), response_type),
            }
            global _seq
            with _lock:
                _seq += 1
                entry["seq"] = _seq
                _items.append(entry)
