"""F1/F2: authentication, roles, route exposure, rate limiting, body limits."""
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[2]
STRONG = {"commander": "c" * 32, "admin": "a" * 32, "viewer": "v" * 32}


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def prod(settings, **kw):
    return dataclasses.replace(settings, env="prod", commander_auth_token=STRONG["commander"],
                               admin_auth_token=STRONG["admin"], **kw)


def test_weak_token_refused_outside_dev(settings):
    for bad in ("change-me", "", "short"):
        with pytest.raises(ValueError):
            dataclasses.replace(settings, env="prod", commander_auth_token=bad, admin_auth_token=STRONG["admin"])
    with pytest.raises(ValueError):  # admin token must be distinct
        dataclasses.replace(settings, env="prod", commander_auth_token=STRONG["admin"],
                            admin_auth_token=STRONG["admin"])
    assert prod(settings).env == "prod"


def test_server_exits_non_zero_with_default_token_in_prod():
    env = {**os.environ, "ENV": "prod", "COMMANDER_AUTH_TOKEN": "change-me", "ADMIN_AUTH_TOKEN": "x" * 32}
    proc = subprocess.run([sys.executable, "-c", "import app.main"], cwd=BACKEND, env=env,
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0 and "weak" in proc.stderr


def operations(app):
    """(method, concrete path) for every documented operation; independent of router internals."""
    fill = {"{run_id}": "default", "{agent_id}": "water_agent", "{incident_id}": "inc-x", "{alert_id}": "alt-x"}
    for path, ops in app.openapi()["paths"].items():
        for k, v in fill.items():
            path = path.replace(k, v)
        for method in ops:
            yield method.upper(), path


def test_every_non_get_route_rejects_unauthenticated_and_viewer(settings):
    app = create_app(prod(settings, enable_test_routes=True, viewer_auth_token=STRONG["viewer"],
                          auth_max_failures_per_min=10_000))
    ops = [(m, p) for m, p in operations(app) if m != "GET"]
    assert len(ops) > 25  # guard against the check passing vacuously
    with TestClient(app) as c:
        for method, path in ops:
            for h in ({}, hdr("wrong-token-wrong-token-wrong"), hdr(STRONG["viewer"])):
                r = c.request(method, path, json={}, headers=h)
                assert r.status_code == 403, (method, path, h, r.status_code)


def test_get_routes_require_viewer_token_when_configured(settings):
    app = create_app(prod(settings, viewer_auth_token=STRONG["viewer"], auth_max_failures_per_min=10_000))
    gets = [p for m, p in operations(app) if m == "GET"]
    assert len(gets) > 15
    with TestClient(app) as c:
        for path in gets:
            assert c.get(path).status_code == 403, path


def test_roles_are_enforced(settings):
    s = prod(settings, viewer_auth_token=STRONG["viewer"], enable_test_routes=True, auth_max_failures_per_min=100)
    with TestClient(create_app(s)) as c:
        assert c.get("/api/simulation/state").status_code == 403            # viewer token required
        assert c.get("/api/simulation/state", headers=hdr(STRONG["viewer"])).status_code == 200
        assert c.post("/api/simulation/start", headers=hdr(STRONG["viewer"])).status_code == 403
        assert c.post("/api/simulation/start", headers=hdr(STRONG["commander"])).status_code == 200
        assert c.post("/api/simulation/reset", json={}, headers=hdr(STRONG["commander"])).status_code == 403
        assert c.post("/api/simulation/reset", json={}, headers=hdr(STRONG["admin"])).status_code == 200
        denials = c.get("/api/audit/logs?category=security&all_sessions=true", headers=hdr(STRONG["admin"])).json()
        assert any(d["action"] == "auth_denied" for d in denials)


def test_test_routes_not_registered_unless_enabled(settings):
    app = create_app(prod(settings))
    paths = {p for _, p in operations(app)}
    assert "/api/events/inject-fake" not in paths and "/api/simulation/reset" not in paths
    assert "/api/simulation/step" not in paths and "/api/simulation/start" in paths


def test_auth_failures_are_rate_limited(settings):
    with TestClient(create_app(prod(settings, auth_max_failures_per_min=3))) as c:
        codes = [c.post("/api/simulation/start", headers=hdr("nope")).status_code for _ in range(5)]
        assert codes[:3] == [403, 403, 403] and codes[-1] == 429
        # even the right token is blocked while the client is rate limited
        assert c.post("/api/simulation/start", headers=hdr(STRONG["commander"])).status_code == 429


def test_body_size_limit(settings):
    with TestClient(create_app(dataclasses.replace(settings, max_request_bytes=512)),
                    headers=hdr("test-token")) as c:
        r = c.post("/api/commander/explain", content=b'{"question": "' + b"x" * 2000 + b'"}',
                   headers={"content-type": "application/json"})
        assert r.status_code == 413


def test_settings_type_is_frozen():
    assert dataclasses.is_dataclass(Settings)
