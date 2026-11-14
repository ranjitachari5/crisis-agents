"""/ws/simulation (default run) and /ws/runs/{run_id} — live event stream.

Server → client envelopes: {"event_seq", "type", "data", "server_time"} where type is one of
snapshot | message | message_status | state | agreement | negotiation | trust_incident | audit | alert | reset |
pong | auth_ok | error.

Client → server:
  {"type": "auth", "token": "<token>"}   first frame, required when VIEWER_AUTH_TOKEN is set (F13)
  {"type": "sync", "since": <event_seq>} replay missed events after a reconnect
  {"type": "ping"}

Inbound frames are capped in size and rate; violations close the socket with
1009 (too big) or 1008 (policy violation).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.simulation.engine import EngineError
from app.websocket.manager import POLICY_VIOLATION, Client, ConnectionManager

log = logging.getLogger(__name__)
router = APIRouter()
MESSAGE_TOO_BIG = 1009


async def _snapshot(ws: WebSocket, runtime, client: Client) -> None:
    async with runtime.lock:
        e = runtime.engine
        payload = {"state": e.snapshot(), "messages": e.messages[-300:],
                   "incidents": [i.to_dict() for i in e.trust.incidents[-50:]]}
    runtime.ws.send_json(client, {"event_seq": runtime.ws.event_seq, "type": "snapshot", "data": payload})


async def _authenticate(ws: WebSocket) -> bool:
    tokens = ws.app.state.tokens
    if tokens.public_read:
        return True
    settings = ws.app.state.settings
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=settings.ws_auth_timeout_s)
        msg = json.loads(raw) if len(raw) <= settings.ws_max_inbound_bytes else {}
    except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        msg = {}
    if not isinstance(msg, dict) or msg.get("type") != "auth" or tokens.role_for(str(msg.get("token", ""))) is None:
        await ws.close(code=POLICY_VIOLATION, reason="authentication required")
        return False
    return True


class _RateLimit:
    def __init__(self, per_s: float):
        self.capacity = max(1.0, per_s)
        self.tokens = self.capacity
        self.rate = per_s
        self.t = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.t) * self.rate)
        self.t = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


async def _serve(ws: WebSocket, run_id: str | None) -> None:
    try:
        runtime = ws.app.state.runs.get(run_id)
    except EngineError:
        await ws.close(code=POLICY_VIOLATION, reason="run not found")
        return
    settings = ws.app.state.settings
    await ws.accept()
    if not await _authenticate(ws):
        return
    manager: ConnectionManager = runtime.ws
    client = await manager.register(ws)
    limiter = _RateLimit(settings.ws_max_inbound_per_s)
    try:
        if not ws.app.state.tokens.public_read:
            manager.send_json(client, {"type": "auth_ok"})
        await _snapshot(ws, runtime, client)
        while not client.closed:
            raw = await ws.receive_text()
            if len(raw) > settings.ws_max_inbound_bytes:
                await ws.close(code=MESSAGE_TOO_BIG, reason="frame too large")
                break
            if not limiter.allow():
                await ws.close(code=POLICY_VIOLATION, reason="rate limit exceeded")
                break
            runtime.touch()
            try:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    raise ValueError
            except ValueError:
                manager.send_json(client, {"type": "error", "data": {"message": "invalid JSON object"}})
                continue
            kind = msg.get("type")
            if kind == "ping":
                manager.send_json(client, {"type": "pong", "event_seq": manager.event_seq})
            elif kind == "auth":
                manager.send_json(client, {"type": "auth_ok"})
            elif kind == "sync":
                try:
                    since = int(msg.get("since", 0))
                except (TypeError, ValueError):
                    manager.send_json(client, {"type": "error", "data": {"message": "since must be an integer"}})
                    continue
                missed = manager.since(since)
                gap = (missed and missed[0]["event_seq"] > since + 1) or (not missed and since < manager.event_seq)
                if gap or len(missed) > manager.client_queue // 2:
                    await _snapshot(ws, runtime, client)  # older than the buffer or too large: full resync
                else:
                    for env in missed:
                        manager.send_json(client, env)
            else:
                manager.send_json(client, {"type": "error", "data": {"message": f"unknown type {kind}"}})
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("websocket error")
    finally:
        manager.disconnect(client)


@router.websocket("/ws/simulation")
async def simulation_ws(ws: WebSocket):
    await _serve(ws, None)


@router.websocket("/ws/runs/{run_id}")
async def run_ws(ws: WebSocket, run_id: str):
    await _serve(ws, run_id)
