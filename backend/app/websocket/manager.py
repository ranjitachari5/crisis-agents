"""WebSocket broadcast hub with sequence numbers, replay buffer and chat pacing.

Engine events are queued in order. Chat messages are released with a small
delay so humans can follow the negotiation live (the computation itself is
instantaneous; pacing affects display only). Clients reconnect with
``{"type": "sync", "since": <event_seq>}`` to receive missed events.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone

from fastapi import WebSocket

log = logging.getLogger(__name__)
PACED = {"message"}


class ConnectionManager:
    def __init__(self, chat_delay_ms: int, buffer_size: int = 2000):
        self.clients: set[WebSocket] = set()
        self.queue: asyncio.Queue | None = None
        self.buffer: deque[dict] = deque(maxlen=buffer_size)
        self.event_seq = 0
        self.chat_delay = chat_delay_ms / 1000
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self.queue = asyncio.Queue()
        self._task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    def publish(self, event_type: str, payload: dict) -> None:
        """Called synchronously from the engine."""
        self.event_seq += 1
        env = {"event_seq": self.event_seq, "type": event_type, "data": payload,
               "server_time": datetime.now(timezone.utc).isoformat()}
        self.buffer.append(env)
        if self.queue is not None:
            self.queue.put_nowait(env)

    async def _pump(self) -> None:
        assert self.queue is not None
        while True:
            env = await self.queue.get()
            await self._broadcast(env)
            if env["type"] in PACED and self.chat_delay > 0 and self.queue.qsize() < 60:
                await asyncio.sleep(self.chat_delay)

    async def _broadcast(self, env: dict) -> None:
        if not self.clients:
            return
        text = json.dumps(env, default=str)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    def since(self, seq: int) -> list[dict]:
        return [e for e in self.buffer if e["event_seq"] > seq]
