"""Load test (F17): REST polling plus N WebSocket clients against a running server.

    python main.py &                                   # server under test
    python -m scripts.load_test --clients 50 --seconds 30 --token change-me

Reports REST latency percentiles, negotiation latency from /api/simulation/metrics and how many WebSocket
clients stayed connected, and exits non-zero if the latency budgets are exceeded.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time

import httpx
import websockets


async def ws_client(url: str, token: str | None, stop: float, counts: dict) -> None:
    try:
        async with websockets.connect(url, max_size=8 * 1024 * 1024) as ws:
            if token:
                await ws.send(json.dumps({"type": "auth", "token": token}))
            while time.monotonic() < stop:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=1)
                    counts["events"] += 1
                except asyncio.TimeoutError:
                    await ws.send(json.dumps({"type": "ping"}))
            counts["survived"] += 1
    except Exception:
        counts["dropped"] += 1


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--clients", type=int, default=50)
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--token", default="change-me", help="commander token (starts the simulation)")
    ap.add_argument("--viewer-token", default=None, help="needed if VIEWER_AUTH_TOKEN is set")
    ap.add_argument("--rest-p95-ms", type=float, default=250)
    ap.add_argument("--negotiation-ms", type=float, default=500)
    a = ap.parse_args()

    headers = {"Authorization": f"Bearer {a.token}"}
    async with httpx.AsyncClient(base_url=a.base, headers=headers, timeout=10) as http:
        await http.post("/api/simulation/start")
        await http.put("/api/simulation/settings", json={"tick_interval_s": 0.5})
        stop = time.monotonic() + a.seconds
        counts = {"events": 0, "survived": 0, "dropped": 0}
        ws_url = a.base.replace("http", "ws", 1) + "/ws/simulation"
        tasks = [asyncio.create_task(ws_client(ws_url, a.viewer_token, stop, counts)) for _ in range(a.clients)]
        lat = []
        while time.monotonic() < stop:
            t = time.perf_counter()
            r = await http.get("/api/simulation/state")
            lat.append((time.perf_counter() - t) * 1000)
            r.raise_for_status()
            await asyncio.sleep(0.05)
        await asyncio.gather(*tasks)
        summary = (await http.get("/api/simulation/metrics")).json()["summary"]

    p95 = statistics.quantiles(lat, n=20)[18]
    neg = summary.get("mean_negotiation_latency_ms") or 0
    print(f"REST: {len(lat)} requests, p50 {statistics.median(lat):.1f} ms, p95 {p95:.1f} ms")
    print(f"WS: {counts['survived']}/{a.clients} clients survived, {counts['dropped']} dropped, "
          f"{counts['events']} events received")
    print(f"negotiation: mean {neg:.1f} ms over {summary.get('negotiations')} negotiations")
    ok = p95 <= a.rest_p95_ms and neg <= a.negotiation_ms and counts["dropped"] == 0
    print("PASS" if ok else "FAIL (latency budget exceeded or clients dropped)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
