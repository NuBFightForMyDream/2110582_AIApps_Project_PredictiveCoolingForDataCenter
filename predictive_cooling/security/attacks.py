"""Simulated cyber attacks on the building network, for the agent demo and the closed-loop study.

All three exploit the same weakness: BACnet/IP and Modbus TCP have no authentication, so a device on the OT
network can read and write points. The PDUs (SNMP v3 with authPriv, a separate network) are assumed intact.
"""
import numpy as np
import pandas as pd

from .. import config as C

ATTACKS = {
    "none": "No attack.",
    "spoofing": "False data injection: the B4–B6 inlet readings (the GPU racks) are rewritten 2.5 °C cooler for the last "
                "hour before the case time.",
    "replay": "Replay: the last hour of room readings is replaced by the readings recorded exactly 24 hours earlier.",
    "setpoint_tamper": "Unauthorized write: 26 °C was written to CRAH-2's BACnet setpoint (AV:1) 30 minutes ago, outside the "
                       "control system.",
}
ATTACK_TITLES = {"none": "No attack", "spoofing": "Sensor spoofing", "replay": "Replay attack",
                 "setpoint_tamper": "Unauthorized setpoint write"}
SPOOF_RACKS = ("B4", "B5", "B6")
SPOOF_DELTA_C = -2.5
ATTACK_MINUTES = 60
REPLAY_OFFSET = pd.Timedelta(hours=24)
TAMPER_SETPOINT_C = 26.0
NOT_REPLAYED = ("crah_setpoint_c",)          # the command log lives in the control system, not on the sensor network


def _recent(index, at, minutes):
    at = pd.Timestamp(at)
    return (index > at - pd.Timedelta(minutes=minutes + 1)) & (index <= at)


def apply_room_attack(frame: pd.DataFrame, log: pd.DataFrame, at, kind: str) -> pd.DataFrame:
    """Spoofing / replay on a window of the room-level sensor log (what every room tool would read)."""
    if kind not in ("spoofing", "replay"):
        return frame
    rows = _recent(frame.index, at, ATTACK_MINUTES)
    if kind == "spoofing":
        for rack in SPOOF_RACKS:
            frame.loc[rows, f"inlet_{rack}_c"] = frame.loc[rows, f"inlet_{rack}_c"] + SPOOF_DELTA_C
    else:
        cols = [c for c in frame.columns if c in log.columns and c not in NOT_REPLAYED]
        source = log[cols].reindex(frame.index[rows] - REPLAY_OFFSET)
        frame.loc[rows, cols] = source.to_numpy()
    if "max_inlet_c" in frame:
        frame["max_inlet_c"] = frame[C.INLET_COLS].max(axis=1, skipna=False)
    return frame


def apply_equipment_attack(frame: pd.DataFrame, at, kind: str) -> pd.DataFrame:
    """Unauthorized BACnet write to CRAH-2's setpoint; the coil starts to follow it."""
    if kind != "setpoint_tamper":
        return frame
    rows = _recent(frame.index, at, 30)
    frame.loc[rows, "CRAH-2.setpoint_c"] = TAMPER_SETPOINT_C
    frame.loc[rows, "CRAH-2.supply_air_c"] = frame.loc[rows, "CRAH-2.supply_air_c"] + np.linspace(1.0, 2.5, int(rows.sum()))
    return frame


def apply_live_attack(reading: dict, ts, attacks, history: dict) -> dict:
    """Closed loop: apply the scenario's attacks to one live reading. `history` holds earlier untouched readings."""
    for start, hours, kind, param in attacks:
        begin = pd.Timestamp(start)
        if not begin <= ts < begin + pd.Timedelta(hours=hours):
            continue
        if kind == "spoofing":
            for rack in param:
                reading[f"inlet_{rack}_c"] += SPOOF_DELTA_C
        elif kind == "replay":
            source = history.get(ts - pd.Timedelta(hours=param))
            if source is not None:
                for key, value in source.items():
                    if key != "timestamp" and not key.startswith("pdu_") and key not in NOT_REPLAYED:
                        reading[key] = value
    return reading
