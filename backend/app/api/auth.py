"""Role-based bearer-token authentication (F1/F2).

Roles:
  viewer    - GET routes and the WebSocket stream (public when VIEWER_AUTH_TOKEN is unset)
  commander - operational control: start/pause, approve, isolate, override, fairness, ...
  admin     - destructive / test tooling: reset, step, event injection, fake-event injection

Tokens are read only from the ``Authorization: Bearer <token>`` header and are
compared in constant time against every configured token. Repeated failures
from one client are rate limited, and every denial is audited.
"""
from __future__ import annotations

import hmac
import logging
import time
from collections import defaultdict, deque
from enum import Enum

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings
from app.observability import AUTH_DENIED
from app.simulation.engine import EngineError

log = logging.getLogger(__name__)


class Role(str, Enum):
    VIEWER = "viewer"
    COMMANDER = "commander"
    ADMIN = "admin"


class FailureLimiter:
    """Sliding one-minute window of authentication failures per client."""

    def __init__(self, max_failures: int, window_s: float = 60.0):
        self.max_failures = max_failures
        self.window_s = window_s
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._fails[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._prune(key, time.monotonic())) >= self.max_failures

    def fail(self, key: str) -> None:
        now = time.monotonic()
        self._prune(key, now).append(now)
        if len(self._fails) > 10_000:  # bound memory under a spray of client addresses
            for k in [k for k, q in self._fails.items() if not q][:5000]:
                del self._fails[k]


class TokenRegistry:
    def __init__(self, settings: Settings):
        entries: list[tuple[str, Role]] = []
        if settings.admin_auth_token:
            entries.append((settings.admin_auth_token, Role.ADMIN))
        # Single-operator dev mode: without a separate admin token the commander token is admin.
        commander_role = Role.ADMIN if (settings.env == "dev" and not settings.admin_auth_token) else Role.COMMANDER
        if settings.commander_auth_token:
            entries.append((settings.commander_auth_token, commander_role))
        if settings.viewer_auth_token:
            entries.append((settings.viewer_auth_token, Role.VIEWER))
        self._entries = [(t.encode(), r) for t, r in entries]
        self.public_read = not settings.viewer_auth_token
        self.limiter = FailureLimiter(settings.auth_max_failures_per_min)

    def role_for(self, token: str | None) -> Role | None:
        """Constant-time lookup: every configured token is compared, no early exit."""
        if not token:
            return None
        tb = token.encode()
        found: Role | None = None
        for t, role in self._entries:
            if hmac.compare_digest(tb, t) and found is None:
                found = role
        return found


_bearer = HTTPBearer(auto_error=False, scheme_name="BearerToken",
                     description="COMMANDER_AUTH_TOKEN, ADMIN_AUTH_TOKEN or VIEWER_AUTH_TOKEN")


def bearer(authorization: str) -> str:
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def _audit_denied(request: Request, reason: str, allowed: set[Role]) -> None:
    AUTH_DENIED.labels(reason=reason).inc()
    detail = {"path": request.url.path, "method": request.method, "reason": reason,
              "required": sorted(r.value for r in allowed),
              "client": request.client.host if request.client else "unknown"}
    log.warning("auth denied: %s", detail)
    runs = getattr(request.app.state, "runs", None)
    if runs is not None:
        try:
            runs.default().engine.audit("security", "unknown", "auth_denied", detail)
        except Exception:  # pragma: no cover - auditing must never mask the 403
            log.exception("failed to audit auth denial")


def require_role(*roles: Role):
    allowed = set(roles)

    async def dependency(request: Request,
                         creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Role:
        reg: TokenRegistry = request.app.state.tokens
        if Role.VIEWER in allowed and reg.public_read:
            return Role.VIEWER
        client = request.client.host if request.client else "unknown"
        if reg.limiter.blocked(client):
            _audit_denied(request, "rate_limited", allowed)
            raise EngineError("TOO_MANY_AUTH_FAILURES", "too many failed authentication attempts", 429)
        token = creds.credentials if creds else ""
        role = reg.role_for(token)
        if role is None or role not in allowed:
            reg.limiter.fail(client)
            _audit_denied(request, "missing_token" if not token else
                          "invalid_token" if role is None else "insufficient_role", allowed)
            raise EngineError("UNAUTHORIZED", "valid bearer token with role "
                              f"{'/'.join(sorted(r.value for r in allowed))} required", 403)
        return role

    dependency.required_roles = frozenset(allowed)  # type: ignore[attr-defined]  # inspected by tests
    return dependency


VIEWER = require_role(Role.VIEWER, Role.COMMANDER, Role.ADMIN)
COMMANDER = require_role(Role.COMMANDER, Role.ADMIN)
ADMIN = require_role(Role.ADMIN)
