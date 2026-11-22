# Guardrails and safety rules

[Architecture index](README.md)

Guards are Python checks, not another model voting. A case either passes all of them or releases nothing (fail closed).

| Guard | Where | Checks |
|---|---|---|
| **G1** request | before any agent | Prompt-injection screen (Unicode NFKC, hidden characters removed, weighted patterns; score ≥ 3 blocks, 1–2 withholds the text from the models); Pydantic request (15-min grid, known racks and devices, length); case time inside both logs |
| **G2** gateway | every tool call and delegation | Skill owner and tool allowlist, phase order (no MPC before inspection, no Cooling Advisor before the Security Analyst and Hardware Engineer, `evaluate_upgrades` only in task `upgrade`), shared tool/model budget, deadline, no data after the case time |
| **G3** verify | after the agents | Rebuilds every window and recomputes: data quality, integrity checks, hardware diagnosis, state, forecast, MPC, safety filter, upgrade plan. The agents' evidence must match; the setpoint must be in range, rate-limited and respect R5 |
| **G4** release | after the answer is composed | Redacts keys, links and e-mails from model notes, flags claims that equipment was changed, HMAC-signs the recommendation (15-min expiry, one-time nonce, evidence hash), seals the trace in a SHA-256 hash chain |

## Safety rules (`safety.py`, in this order)

| Rule | When | Then |
|---|---|---|
| R1 Missing data | any rack inlet missing | head to the fallback setpoint (20 °C, the proven fixed setting) |
| R2 Unfamiliar | inputs far outside the training range | fallback setpoint |
| R6 Untrusted | the Security Analyst's verdict is untrusted | never warmer than now or than the fallback |
| R5 Hardware | the Hardware Engineer's constraint is `no_raise` / `fallback` | never warmer than now / also never warmer than the fallback |
| R3 Too hot now | measured hottest inlet ≥ 26.7 °C | cool by 2 °C at once |
| R4 Limits | always | ±1 °C per 15 min (−2 °C under R3), within 16–24 °C |

R5 receives no constraint in the closed-loop study (no hardware faults there); R6 runs in the closed-loop AI controller and
never fires outside the attack scenarios.

## Failure codes

| Status | Codes |
|---|---|
| `security_alert` | `PROMPT_INJECTION_BLOCKED` (G1); untrusted data found by G3: `SPOOFED_READING`, `REPLAYED_READINGS`, `SETPOINT_TAMPER` (decision `fallback`) |
| `insufficient_data` | `NO_READING_AT_CASE_TIME`, `MISSING_SENSOR:<rack>`, `STUCK_SENSOR:<rack>`, … (decision `fallback`) |
| `budget_exceeded` | `TOOL_BUDGET_EXCEEDED`, `MODEL_BUDGET_EXCEEDED`, `DEADLINE_EXCEEDED` |
| `failed` | G1 `CASE_TIME_OUTSIDE_SENSOR_LOG`, `CASE_TIME_OUTSIDE_EQUIPMENT_LOG`; G2 `TOOL_NOT_ALLOWED`, `SKILL_OWNER_MISMATCH`, `UNKNOWN_TOOL`, `DATA_NOT_INSPECTED`, `EQUIPMENT_NOT_READ`, `EQUIPMENT_NOT_INSPECTED`, `INTEGRITY_NOT_CHECKED`, `UPGRADES_NOT_IN_SCOPE`, `UPGRADE_STUDY_MISSING`; G3 `EVIDENCE_CHANGED`, `ANALYSIS_EVIDENCE_MISMATCH`, `PROPOSAL_EVIDENCE_MISMATCH`, `EQUIPMENT_EVIDENCE_MISMATCH`, `SECURITY_EVIDENCE_MISMATCH`, `UPGRADE_EVIDENCE_MISMATCH`, `SETPOINT_OUT_OF_POLICY`; models `ONE_TOOL_CALL_REQUIRED`, `MODEL_REFUSED`, `MODEL_OUTPUT_TRUNCATED`, `GEMINI_NOT_CONFIGURED`, `CLAUDE_NOT_CONFIGURED`, `WORKFLOW_ERROR` |

Every guard has a test that makes it fire (`tests/test_agents.py`, `test_hardware.py`, `test_security.py`, `test_upgrades.py`).
