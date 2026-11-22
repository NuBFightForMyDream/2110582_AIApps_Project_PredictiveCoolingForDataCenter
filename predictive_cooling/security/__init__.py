"""Security layer: attacks the room's network allows, and the defences the agents and guards use.

    prompt_guard.py  G1 prompt-injection screen of the operator question; G4 redaction of model notes
    integrity.py     ML physics-consistency model (inlet vs PDU power + supply air) and replay detection
    commands.py      command-channel audit (device setpoint vs the commanded one) and the trust verdict
    attacks.py       simulated attacks: sensor spoofing, replay, unauthorised setpoint write
    signing.py       HMAC-signed recommendations with expiry and nonce, and the actuator-side verifier
    audit.py         SHA-256 hash-chained trace
    ratelimit.py     sliding-window limiter for the paid model modes
    posture.py       protocol posture and the STRIDE threat model

The Security Analyst agent (skill S7) reads the integrity and command evidence and reports to the Supervisor;
safety rule R6 never lets untrusted data warm the room.
"""
