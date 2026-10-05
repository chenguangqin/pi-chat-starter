from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse


@dataclass(frozen=True)
class Identity:
    tenant_id: str
    user_id: str


class IdentityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        if request.url.path == "/api/health":
            return await call_next(request)

        tenant_id = request.headers.get("x-tenant-id", "").strip()
        user_id = request.headers.get("x-user-id", "").strip()

        if not tenant_id or not user_id:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing X-Tenant-ID or X-User-ID header"},
            )

        request.state.identity = Identity(tenant_id=tenant_id, user_id=user_id)
        return await call_next(request)


def get_identity(request: Request) -> Identity:
    return request.state.identity
