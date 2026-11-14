"""Entry point: `python main.py` or `uvicorn main:app --reload`.

Simulation state lives in this process (one asyncio lock per run), so the
server must run as a single worker: several workers would silently split
state. Scale by running separate instances, not `--workers N`.
"""
import os
import sys

import uvicorn

from app.main import app  # noqa: F401

if __name__ == "__main__":
    workers = int(os.getenv("WEB_CONCURRENCY", os.getenv("UVICORN_WORKERS", "1")) or 1)
    if workers != 1:
        sys.exit("CRISIS AGENTS keeps simulation state in-process: run with exactly one worker "
                 f"(WEB_CONCURRENCY={workers}).")
    uvicorn.run("main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")),
                reload=os.getenv("RELOAD", "false").lower() == "true", workers=1)
