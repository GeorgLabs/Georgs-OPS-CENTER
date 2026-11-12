"""M4 - security headers. Cheap, and they switch off whole classes of browser attacks."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    """TODO M4 - add these headers to every HTTP response:

    X-Content-Type-Options: nosniff        browser must not guess content types
    X-Frame-Options: DENY                  nobody may put us in an <iframe> (clickjacking)
    Referrer-Policy: no-referrer           do not leak our URLs to other sites
    Content-Security-Policy: <see below>   the browser only runs scripts/styles from OUR origin
    Cache-Control: no-store                for everything under /api/ (no secrets in caches)

    CSP to use: default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none';
    frame-ancestors 'none'.  Skip the CSP for /docs (Swagger UI needs an inline script).
    A raw ASGI middleware looks like this: wrap `send`, and edit the "http.response.start" message
    with MutableHeaders(scope=message).
    """

    CSP = (
        "default-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        #await self.app(scope, receive, send)  # TODO M4: right now it changes nothing
            #@@ solution
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                if not path.startswith(("/docs", "/redoc")):
                    headers["Content-Security-Policy"] = self.CSP
                if path.startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)

