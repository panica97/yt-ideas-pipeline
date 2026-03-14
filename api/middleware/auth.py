"""API key authentication middleware."""

from __future__ import annotations

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api.config import settings

# Paths that do NOT require authentication.
_PUBLIC_PATHS = frozenset({
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
})


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Check ``X-API-Key`` header on every request except public paths."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Allow public paths and the OpenAPI docs prefix.
        if path in _PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # WebSocket upgrade requests are handled separately (query param auth).
        if request.scope.get("type") == "websocket":
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key or api_key != settings.DASHBOARD_API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "API key invalida o no proporcionada"},
            )

        return await call_next(request)
