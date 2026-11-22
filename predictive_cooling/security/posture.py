"""Static security posture of the room's protocols and the STRIDE threat model (shown on the Security page)."""
from ..hardware.registry import DEVICES

PROTOCOLS = {
    "BACnet/IP": {"authentication": "None", "encryption": "None", "risk": "High",
                  "why": "Any host on the OT network can read and WRITE points (e.g. a CRAH setpoint).",
                  "mitigation": "BACnet Secure Connect (TLS 1.3, device certificates), or isolate in an OT VLAN with a "
                                "write allowlist; this project's gateway is read-only"},
    "Modbus TCP": {"authentication": "None", "encryption": "None", "risk": "High",
                   "why": "Registers can be read and written by anyone who reaches TCP 502.",
                   "mitigation": "Modbus/TCP Security (TLS, X.509 roles, TCP 802), or a read-only protocol gateway / "
                                 "firewall allowlist; physics checks catch forged values"},
    "SNMP v3": {"authentication": "SHA-2 HMAC (authPriv)", "encryption": "AES-128", "risk": "Low",
                "why": "Secure if configured authPriv and v1/v2c communities are disabled.",
                "mitigation": "authPriv only, unique users per device, disable v1/v2c; PDUs are the integrity model's "
                              "trusted second source"},
}

STRIDE = [
    ("Spoofing", "Forged rack-inlet readings (false data injection)", "Integrity model (inlet vs PDU power + supply air) → R6"),
    ("Spoofing", "Replayed recordings of a quiet period", "Exact-repeat detection over 7 days → R6"),
    ("Tampering", "Unauthorised write to a CRAH setpoint", "Command-channel audit (device setpoint vs commanded) → R6"),
    ("Tampering", "Altered recommendation on its way to equipment", "HMAC-SHA256 signature, 15-min expiry, one-time nonce"),
    ("Repudiation", "Disputed or edited case history", "SHA-256 hash-chained trace; Supabase history"),
    ("Information disclosure", "API keys leaked through model output", "Keys only in server-side secrets; G4 redacts keys, links, e-mails"),
    ("Denial of service", "Flooding the paid model modes", "Per-session and per-app rate limits; tool/model budgets; deadlines"),
    ("Elevation of privilege", "Prompt injection steering the agents", "G1 prompt screen; G2 tool allowlists; no actuation tool; G3 recompute"),
]


def device_posture() -> list[dict]:
    return [{"Device": d.id, "Protocol": d.protocol, "Endpoint": d.endpoint, **{k: PROTOCOLS[d.protocol][k] for k in
            ("authentication", "encryption", "risk")}} for d in DEVICES]
