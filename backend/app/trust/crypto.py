"""HMAC message signing used to authenticate agent messages."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()


def sign(payload: dict[str, Any], key: bytes) -> str:
    return hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()


def verify(payload: dict[str, Any], signature: str | None, key: bytes | None) -> bool:
    if not signature or key is None:
        return False
    return hmac.compare_digest(sign(payload, key), signature)
