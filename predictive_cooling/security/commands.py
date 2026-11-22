"""Command-channel audit: is every CRAH running the setpoint the control system actually commanded?

The room log's `crah_setpoint_c` is the authorised command (the decision made at each step, applied for the next
15 minutes). Each CRAH reports its active setpoint over BACnet (AV:1). A difference means somebody wrote to the
device outside the control system: an unauthorised write, since BACnet/IP itself does not authenticate writers.
The sensor gateway in this project is read-only (it has no write function), so it cannot be that writer.
"""
import pandas as pd



DEVICES = ("CRAH-1", "CRAH-2")
TOLERANCE_C = 0.05


def audit_commands(room: pd.DataFrame, equipment: pd.DataFrame, at, hours: float = 2.0) -> dict:
    at = pd.Timestamp(at)
    start = at - pd.Timedelta(hours=hours)
    authorised = room["crah_setpoint_c"].shift(1).loc[start:at]         # in use during the interval ending at t
    findings, compared = [], 0
    for device in DEVICES:
        reported = equipment[f"{device}.setpoint_c"].reindex(authorised.index)
        both = authorised.notna() & reported.notna()
        compared += int(both.sum())
        bad = both & ((reported - authorised).abs() > TOLERANCE_C)
        if bad.any():
            first = bad[bad].index[0]
            findings.append({"code": "SETPOINT_TAMPER", "severity": "critical", "racks": [], "device": device,
                             "value": float(reported.loc[bad].iloc[-1]), "unit": "°C on the device",
                             "limit": float(authorised.loc[bad].iloc[-1]),
                             "detail": f"{device} reports setpoint {reported.loc[bad].iloc[-1]:g} °C but the control system "
                                       f"commanded {authorised.loc[bad].iloc[-1]:g} °C (since {first:%H:%M})",
                             "action": "Unauthorised BACnet write: restore the setpoint, find the writer, restrict BACnet "
                                       "write access (BACnet/SC or a firewall allowlist)"})
    return {"trusted": not findings, "findings": findings, "readings_compared": compared, "window_hours": hours,
            "gateway_can_write": False}


def verdict(integrity: dict, commands: dict, screen: dict | None = None) -> dict:
    """Combine the Security Analyst's evidence. Any critical finding makes the data untrusted (safety rule R6)."""
    findings = list(integrity["findings"]) + list(commands["findings"])
    if screen and screen.get("verdict") == "flagged":
        findings.append({"code": "PROMPT_INJECTION_FLAGGED", "severity": "warning", "racks": [], "value": screen["score"],
                         "unit": "score", "limit": None,
                         "detail": "operator question withheld from the models: " + ", ".join(m["category"] for m in screen["matches"]),
                         "action": "Review who submitted the question"})
    trusted = not any(f["severity"] == "critical" for f in findings)
    return {"verdict": "trusted" if trusted else "untrusted", "trusted": trusted,
            "codes": sorted({f["code"] for f in findings}), "findings": findings}


def describe(f: dict) -> str:
    return f"{f['code']}: {f['detail']}"


def summary_note(sec: dict) -> str:
    if sec["trusted"] and not sec["findings"]:
        return "Sensor data is consistent with the PDU power and supply air, no replayed readings, CRAH setpoints match the commands."
    return ("Data UNTRUSTED. " if not sec["trusted"] else "Data trusted. ") + " ".join(describe(f) + "." for f in sec["findings"])



