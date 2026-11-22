"""Tamper-evident audit trail: every trace event is chained to the previous one by SHA-256.

    hash_n = sha256(hash_{n-1} + canonical JSON of event n without its hash),   hash_0 = 64 x "0"

Changing, removing or reordering any stored event breaks every later hash, so a case record (e.g. in Supabase)
can be checked after the fact with `verify_chain`.
"""
import hashlib

from .signing import canonical

GENESIS = "0" * 64


def link(previous: str, event: dict) -> str:
    body = {k: v for k, v in event.items() if k != "hash"}
    return hashlib.sha256(previous.encode() + canonical(body)).hexdigest()


def verify_chain(events: list[dict]) -> tuple[bool, int | None]:
    """(intact, step of the first event that does not match)."""
    previous = GENESIS
    for event in events:
        expected = link(previous, event)
        if event.get("hash") != expected:
            return False, event.get("step")
        previous = expected
    return True, None
