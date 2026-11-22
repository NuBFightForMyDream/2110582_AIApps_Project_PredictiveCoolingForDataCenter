# Security layer

[Architecture index](README.md)

**Threat model.** BACnet/IP and Modbus TCP have no authentication, so anyone on that network can forge a reading, replay a
recording or write a setpoint. The dangerous lie is a rack reported *cooler* than it is. The PDUs (SNMP v3 authPriv, separate
network) are assumed intact; an attacker controlling both networks is out of scope.

| Defence | Code | How |
|---|---|---|
| Integrity model (ML) | `security/integrity.py` | Per rack, least squares on the training weeks: inlet ≈ f(supply air, rack PDU power; now and 3 lags). Residual std 0.18 °C. Flagged when > 1.5 °C cooler than expected once or > 1.0 °C twice in a row. 0 false alarms on 2,682 validation + test readings |
| Replay | same | A 12-inlet reading vector exactly equal to an earlier one (agents: 26 h window; closed loop: 7 days) |
| Command audit | `security/commands.py` | Each CRAH's BACnet setpoint must equal the commanded one |
| R6 | `safety.py` | Untrusted → never warmer than now or the fallback; status `security_alert`, AI withheld |
| G1 prompt screen | `security/prompt_guard.py` | NFKC normalisation, hidden characters removed, weighted patterns (override, secret exfiltration, guard bypass, tool manipulation, out-of-policy setpoints, markup, encoded payloads) |
| G4 output guard | same | Redacts API keys (incl. the configured secrets' real values), JWTs, links, e-mails; flags actuation claims |
| Signed answer | `security/signing.py` | HMAC-SHA256 (`COMMAND_SIGNING_KEY`, else an ephemeral per-process key), 15-min expiry, one-time nonce, evidence hash; `CommandVerifier` = the actuator-gateway check |
| Audit chain | `security/audit.py` | Each trace event carries sha256(previous hash + event) |
| Rate limit | `security/ratelimit.py` | Paid model modes: 5 cases / 10 min per session, 40 / hour per app |

**Closed-loop attack study** (minutes with a true inlet above 27 °C, 14 test days): sensor spoofing — fixed 0, rule 450,
AI without the check 465, AI 0; replay — 0, 435, 390, 0. The monitor never fires in the four non-attack scenarios, so every
other result is unchanged with it on. STRIDE table and protocol posture: `security/posture.py` (Security page).
