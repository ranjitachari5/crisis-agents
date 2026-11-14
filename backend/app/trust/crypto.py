"""Ed25519 message signing (F3).

Each agent holds only its own private key (``SigningKey``). The trust engine
holds only public keys (``PublicKeyRegistry``), so compromising the verifier
does not let an attacker sign as any agent, and signatures are
non-repudiable. Messages are signed over canonical JSON bytes (sorted keys,
fixed separators) that include the key id, sender, message id, per-agent
sequence number and timestamp.
"""
from __future__ import annotations

import json
import secrets
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ALGORITHM = "Ed25519"


def canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


@dataclass
class SigningKey:
    """Agent-side private key. Never handed to the trust engine."""
    kid: str
    _sk: Ed25519PrivateKey = field(repr=False)

    def sign(self, payload: dict[str, Any]) -> str:
        return self._sk.sign(canonical(payload)).hex()

    def public_key(self) -> Ed25519PublicKey:
        return self._sk.public_key()


def generate(agent_id: str) -> SigningKey:
    return SigningKey(f"{agent_id}#{secrets.token_hex(4)}", Ed25519PrivateKey.generate())


def verify(payload: dict[str, Any], signature: str | None, public_key: Ed25519PublicKey | None) -> bool:
    if not signature or public_key is None:
        return False
    try:
        public_key.verify(bytes.fromhex(signature), canonical(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


class PublicKeyRegistry:
    """Verifier-side registry: agent id -> active key ids -> public keys.

    Up to ``MAX_ACTIVE`` keys per agent are valid at once (rotation grace
    window). Older keys are revoked automatically when a new one is
    registered; ``revoke_agent`` revokes all of an agent's keys (isolation).
    """
    MAX_ACTIVE = 2

    def __init__(self) -> None:
        self._keys: dict[str, OrderedDict[str, Ed25519PublicKey]] = {}
        self.revoked: set[str] = set()

    def register(self, agent_id: str, kid: str, public_key: Ed25519PublicKey) -> None:
        keys = self._keys.setdefault(agent_id, OrderedDict())
        keys[kid] = public_key
        while len(keys) > self.MAX_ACTIVE:
            old, _ = keys.popitem(last=False)
            self.revoked.add(old)

    def revoke_agent(self, agent_id: str) -> list[str]:
        keys = self._keys.get(agent_id)
        if not keys:
            return []
        kids = list(keys)
        self.revoked.update(kids)
        keys.clear()
        return kids

    def public_key(self, agent_id: str, kid: str | None) -> Ed25519PublicKey | None:
        if not kid or kid in self.revoked:
            return None
        keys = self._keys.get(agent_id)
        return keys.get(kid) if keys else None

    def is_revoked(self, kid: str | None) -> bool:
        return bool(kid) and kid in self.revoked

    def active_kids(self, agent_id: str) -> list[str]:
        return list(self._keys.get(agent_id, {}))

    def participants(self) -> list[str]:
        return list(self._keys)

    def __contains__(self, agent_id: object) -> bool:
        return agent_id in self._keys
