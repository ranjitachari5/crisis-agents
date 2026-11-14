"""Entry point: `python main.py` or `uvicorn main:app --reload`."""
import os

import uvicorn

from app.main import app  # noqa: F401

if __name__ == "__main__":
    uvicorn.run("main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")),
                reload=os.getenv("RELOAD", "false").lower() == "true")
