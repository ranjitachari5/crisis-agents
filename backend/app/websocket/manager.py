"""WebSocket broadcast hub with sequence numbers, a bounded replay buffer,
per-client backpressure and chat pacing (F13).

Engine events are queued in order. Chat messages are released with a small
delay so humans can follow the negotiation live (the computation itself is
instantaneous; pacing affects display only). Clients reconnect with
``{"type": "sync", "since": <event_seq>}`` to receive missed events; if that
is older than the ring buffer they get a fresh snapshot instead.

Every client has a bounded outbound queue drained by its own writer task, so
one slow client can neither block the broadcast nor grow memory: when its
queue is full it is disconnected with close code 1008.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone

from fastapi import WebSocket

from app.observability import WS_DROPPED

log = logging.getLogger(__name__)
PACED = {"message"}
POLICY_VIOLATION = 1008


class Client:
    def __init__(self, ws: WebSocket, maxsize: int):
        self.ws = ws
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)
        self.task: asyncio.Task | None = None
        self.closed = False


class ConnectionManager:
    def __init__(self, chat_delay_ms: int, buffer_size: int = 2000, client_queue: int = 256):
        self.clients: set[Client] = set()
        self.queue: asyncio.Queue | None = None
        self.buffer: deque[dict] = deque(maxlen=buffer_size)
        self.event_seq = 0
        self.chat_delay = chat_delay_ms / 1000
        self.client_queue = client_queue
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self.queue = asyncio.Queue()
        self._task = asyncio.create_task(self._pump())

    async def stop(self) -> None:
        for c in list(self.clients):
            await self._close(c, 1001, "server shutting down")
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
            if self.clients:
                text = json.dumps(env, default=str)
                for c in list(self.clients):
                    self.send(c, text)
            if env["type"] in PACED and self.chat_delay > 0 and self.queue.qsize() < 60:
                await asyncio.sleep(self.chat_delay)

    # ------------------------------------------------------------ clients
    async def register(self, ws: WebSocket) -> Client:
        c = Client(ws, self.client_queue)
        c.task = asyncio.create_task(self._writer(c))
        self.clients.add(c)
        return c

    def send(self, c: Client, text: str) -> bool:
        """Non-blocking enqueue. A full queue means a slow consumer: drop it."""
        if c.closed:
            return False
        try:
            c.queue.put_nowait(text)
            return True
        except asyncio.QueueFull:
            WS_DROPPED.labels(reason="slow_consumer").inc()
            log.warning("dropping slow websocket client (queue of %d full)", self.client_queue)
            asyncio.get_running_loop().create_task(self._close(c, POLICY_VIOLATION, "slow consumer"))
            return False

    def send_json(self, c: Client, obj: dict) -> bool:
        return self.send(c, json.dumps(obj, default=str))

    async def _writer(self, c: Client) -> None:
        try:
            while True:
                text = await c.queue.get()
                await c.ws.send_text(text)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.disconnect(c)

    async def _close(self, c: Client, code: int, reason: str) -> None:
        if c.closed:
            return
        self.disconnect(c)
        try:
            await c.ws.close(code=code, reason=reason)
        except Exception:
            pass

    def disconnect(self, c: Client) -> None:
        c.closed = True
        self.clients.discard(c)
        if c.task and c.task is not asyncio.current_task():
            c.task.cancel()

    def since(self, seq: int) -> list[dict]:
        return [e for e in self.buffer if e["event_seq"] > seq]
