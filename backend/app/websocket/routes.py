"""/ws/simulation — live event stream.

Server → client envelopes: {"event_seq", "type", "data", "server_time"} where type is one of
snapshot | message | message_status | state | agreement | negotiation | trust_incident | audit | alert | reset | pong.
Client → server: {"type": "sync", "since": <event_seq>} to replay missed events after reconnect,
{"type": "ping"}.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger(__name__)
router = APIRouter()


async def _snapshot(ws: WebSocket) -> None:
    runtime = ws.app.state.runtime
    async with runtime.lock:
        e = runtime.engine
        payload = {"state": e.snapshot(), "messages": e.messages[-300:],
                   "incidents": [i.to_dict() for i in e.trust.incidents[-50:]]}
    await ws.send_text(json.dumps({"event_seq": runtime.ws.event_seq, "type": "snapshot", "data": payload},
                                  default=str))


@router.websocket("/ws/simulation")
async def simulation_ws(ws: WebSocket):
    manager = ws.app.state.ws
    await manager.connect(ws)
    try:
        await _snapshot(ws)
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "data": {"message": "invalid JSON"}}))
                continue
            kind = msg.get("type")
            if kind == "ping":
                await ws.send_text(json.dumps({"type": "pong", "event_seq": manager.event_seq}))
            elif kind == "sync":
                since = int(msg.get("since", 0))
                missed = manager.since(since)
                if missed and missed[0]["event_seq"] > since + 1 or (not missed and since < manager.event_seq):
                    await _snapshot(ws)  # gap larger than buffer: full resync
                else:
                    for env in missed:
                        await ws.send_text(json.dumps(env, default=str))
            else:
                await ws.send_text(json.dumps({"type": "error", "data": {"message": f"unknown type {kind}"}}))
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("websocket error")
    finally:
        manager.disconnect(ws)
