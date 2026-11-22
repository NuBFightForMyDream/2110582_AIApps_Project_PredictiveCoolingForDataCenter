"""Signed recommendations: what a downstream actuator gateway would accept (G4).

Nothing in this project writes to equipment. If a site ever connects one, it should only accept setpoints that
(1) carry a valid HMAC-SHA256 signature from this system's key, (2) are not expired, (3) were never used before
(nonce), and (4) stay inside the 16–24 °C policy. `CommandVerifier` is that gateway's check.

The key comes from COMMAND_SIGNING_KEY (Streamlit secrets or environment; generate one with
`python -c "import secrets; print(secrets.token_hex(32))"`). Without it, a random key is made per process and the
key id says "ephemeral": signatures then prove integrity within one running app, not across restarts.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
from uuid import uuid4

from .. import config as C

ALG = "HMAC-SHA256"
VALID_MINUTES = 15                    # one control step
_EPHEMERAL = secrets.token_bytes(32)


def canonical(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def digest(data) -> str:
    return hashlib.sha256(canonical(data)).hexdigest()


def signing_key() -> tuple[bytes, str]:
    raw = os.getenv("COMMAND_SIGNING_KEY", "")
    if raw:
        return raw.encode(), "site-" + hashlib.sha256(raw.encode()).hexdigest()[:8]
    return _EPHEMERAL, "ephemeral-" + hashlib.sha256(_EPHEMERAL).hexdigest()[:8]


def _sign(key: bytes, payload: dict) -> str:
    return hmac.new(key, canonical(payload), hashlib.sha256).hexdigest()


def sign_command(case_id, case_time, setpoint, decision, evidence_sha256, policy, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    payload = {
        "type": "supply_air_setpoint_recommendation", "site": "zone-a", "target": "CRAH-1, CRAH-2 · setpoint_c (BACnet AV:1)",
        "value_c": float(setpoint), "decision": decision, "case_id": case_id, "case_time": str(case_time),
        "issued_at": now.isoformat(timespec="seconds"), "valid_until": (now + timedelta(minutes=VALID_MINUTES)).isoformat(timespec="seconds"),
        "nonce": uuid4().hex, "evidence_sha256": evidence_sha256, "policy": policy,
    }
    key, key_id = signing_key()
    return {"alg": ALG, "key_id": key_id, "payload": payload, "signature": _sign(key, payload)}


class CommandVerifier:
    """The actuator-gateway side: signature, key, expiry, one-time nonce and the setpoint range."""

    def __init__(self, key: bytes | None = None, key_id: str | None = None):
        if key is None:
            key, key_id = signing_key()
        self.key, self.key_id = key, key_id
        self.seen = set()

    def verify(self, command: dict, now=None) -> tuple[bool, str]:
        now = now or datetime.now(timezone.utc)
        payload = command.get("payload", {})
        if command.get("alg") != ALG:
            return False, "UNSUPPORTED_ALGORITHM"
        if self.key_id and command.get("key_id") != self.key_id:
            return False, "UNKNOWN_KEY"
        if not hmac.compare_digest(_sign(self.key, payload), str(command.get("signature", ""))):
            return False, "BAD_SIGNATURE"
        if now > datetime.fromisoformat(payload["valid_until"]):
            return False, "EXPIRED"
        if payload["nonce"] in self.seen:
            return False, "NONCE_REUSED"
        if not C.SP_MIN <= payload["value_c"] <= C.SP_MAX:
            return False, "OUT_OF_POLICY"
        self.seen.add(payload["nonce"])
        return True, "OK"
