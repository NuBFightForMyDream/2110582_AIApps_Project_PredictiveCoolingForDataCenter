"""Sensor-integrity checks against false data injection and replay attacks.

BACnet/IP and Modbus TCP carry no authentication, so anyone on the building network can rewrite a reading. The
dangerous lie is a rack inlet reported COOLER than it is: the AI would then run the room warmer and overheat it.

1. Physics consistency (machine learning). Per rack, a linear model trained on the training weeks predicts the
   inlet temperature from signals of OTHER systems: the supply-air temperature (BMS) and that rack's PDU power (SNMP,
   a separate network), now and over the last 45 minutes (the room's ~25-minute thermal lag). Residual std is about
   0.18 °C. Only the cooler-than-physics side raises an alarm:
       flagged when residual < -1.5 °C once, or < -1.0 °C on two readings in a row
   (zero false alarms on the validation and test weeks). To pass, an attacker must also forge the PDUs.
2. Replay. Twelve noisy inlet readings never repeat exactly. A reading vector identical to one already seen means
   recorded data is being played back.
"""
from collections import deque

import numpy as np
import pandas as pd

from .. import config as C
from ..preprocess import STUCK_READINGS, VALID_RANGE

LAGS = 4                         # now, -15, -30, -45 min
SINGLE_LIMIT_C = -1.5            # one reading this much cooler than physics -> flagged
REPEAT_LIMIT_C = -1.0            # two readings in a row this much cooler -> flagged
REPLAY_LOOKBACK = 7 * C.STEPS_PER_DAY


def pdu_frame(equipment: pd.DataFrame, index=None) -> pd.DataFrame:
    """Rack power from the PDU columns of the equipment historian, one column per rack."""
    out = pd.DataFrame({r: equipment[f"PDU-{r}.power_kw"] for r in C.RACKS})
    return out if index is None else out.reindex(index)


def _features(supply: np.ndarray, power: np.ndarray) -> np.ndarray:
    """Rows = time; columns = [1, supply lags 0..3, power lags 0..3]. Rows without full lags are NaN."""
    n = len(supply)
    cols = [np.ones(n)]
    for series in (supply, power):
        for k in range(LAGS):
            lagged = np.full(n, np.nan)
            lagged[k:] = series[:n - k] if k else series
            cols.append(lagged)
    return np.column_stack(cols)


class IntegrityModel:
    """inlet_r ≈ f(supply air, PDU power of rack r) — fit by least squares on the training weeks."""

    def __init__(self):
        self.coef: dict[str, np.ndarray] = {}
        self.residual_std: dict[str, float] = {}
        self.validation: dict = {}

    def fit(self, room: pd.DataFrame, power: pd.DataFrame):
        for rack in C.RACKS:
            x = _features(room["supply_air_c"].to_numpy(float), power[rack].to_numpy(float))
            y = room[f"inlet_{rack}_c"].to_numpy(float)
            ok = np.isfinite(x).all(axis=1) & np.isfinite(y)
            self.coef[rack], *_ = np.linalg.lstsq(x[ok], y[ok], rcond=None)
            self.residual_std[rack] = float(np.std(y[ok] - x[ok] @ self.coef[rack]))
        return self

    def residuals(self, room: pd.DataFrame, power: pd.DataFrame) -> pd.DataFrame:
        """Measured minus predicted inlet (°C) per rack; negative = cooler than physics allows."""
        supply = room["supply_air_c"].to_numpy(float)
        out = {}
        for rack in C.RACKS:
            x = _features(supply, power[rack].to_numpy(float))
            out[rack] = room[f"inlet_{rack}_c"].to_numpy(float) - x @ self.coef[rack]
        return pd.DataFrame(out, index=room.index)

    def predict_one(self, rack, supply_lags, power_lags):
        """supply_lags / power_lags: newest first, LAGS values each."""
        return float(self.coef[rack] @ np.concatenate([[1.0], supply_lags, power_lags]))

    @classmethod
    def from_data(cls, clean_log: pd.DataFrame, equipment: pd.DataFrame):
        """Fit on the training weeks; record residual spread and false alarms on validation and test weeks."""
        power = pdu_frame(equipment, clean_log.index)
        train = clean_log.index < pd.Timestamp(C.TRAIN_END)
        model = cls().fit(clean_log[train], power[train])
        for name, mask in (("validation", (clean_log.index >= pd.Timestamp(C.TRAIN_END)) & (clean_log.index < pd.Timestamp(C.VAL_END))),
                           ("test", clean_log.index >= pd.Timestamp(C.VAL_END))):
            res = model.residuals(clean_log[mask], power[mask])
            alarms = flags(res).any(axis=1)
            model.validation[name] = {"readings": int(res.notna().all(axis=1).sum()), "false_alarms": int(alarms.sum()),
                                      "min_residual_c": round(float(res.min().min()), 3),
                                      "residual_std_c": round(float(res.stack().std()), 3)}
        return model


def flags(residuals: pd.DataFrame) -> pd.DataFrame:
    """True where a rack's reading is implausibly cool (single deep dip, or two moderate dips in a row)."""
    single = residuals < SINGLE_LIMIT_C
    repeat = (residuals < REPEAT_LIMIT_C) & (residuals.shift(1) < REPEAT_LIMIT_C)
    return single | repeat


def _inlet_key(values):
    if any(v is None or not np.isfinite(v) for v in values):
        return None
    return tuple(round(float(v), 3) for v in values)


def replay_matches(room: pd.DataFrame, at, recent=4) -> list[dict]:
    """Recent reading vectors (12 inlets) that exactly equal an earlier one in the window."""
    inlets = room[C.INLET_COLS]
    at = pd.Timestamp(at)
    cut = at - pd.Timedelta(minutes=C.STEP_MINUTES * (recent - 1))
    earlier = {}
    for t, row in inlets[inlets.index < cut].iterrows():
        key = _inlet_key(row.to_numpy())
        if key is not None:
            earlier.setdefault(key, t)
    out = []
    for t, row in inlets[(inlets.index >= cut) & (inlets.index <= at)].iterrows():
        key = _inlet_key(row.to_numpy())
        if key is not None and key in earlier:
            out.append({"reading": f"{t:%d %b %H:%M}", "same_as": f"{earlier[key]:%d %b %H:%M}"})
    return out


def _trusted_room(room: pd.DataFrame) -> pd.DataFrame:
    """Drop what the data-quality rules already reject (impossible values, stuck sensors): that is not an attack."""
    frame = room.copy()
    for col, (low, high) in VALID_RANGE.items():
        if col in frame and col != "crah_setpoint_c":
            frame.loc[(frame[col] < low) | (frame[col] > high), col] = np.nan
    for col in C.INLET_COLS:
        tail = frame[col].iloc[-STUCK_READINGS:]
        if tail.notna().all() and tail.nunique() == 1:
            frame[col] = np.nan
    return frame


def check_window(model: IntegrityModel, room: pd.DataFrame, equipment: pd.DataFrame, at) -> dict:
    """Security Analyst evidence for one case: physics residuals at the case time and replay matches."""
    at = pd.Timestamp(at)
    frame = _trusted_room(room)
    res = model.residuals(frame, pdu_frame(equipment, frame.index))
    flagged = flags(res)
    now = res.loc[at] if at in res.index else pd.Series(np.nan, index=C.RACKS)
    recent = flagged.loc[at - pd.Timedelta(minutes=C.STEP_MINUTES):at].any()
    findings = []
    spoofed = [r for r in C.RACKS if bool(recent.get(r, False))]
    if spoofed:
        worst = float(res.loc[at - pd.Timedelta(minutes=C.STEP_MINUTES):at, spoofed].min().min())
        findings.append({"code": "SPOOFED_READING", "severity": "critical", "racks": spoofed, "value": round(worst, 2),
                         "unit": "°C vs physics", "limit": SINGLE_LIMIT_C,
                         "detail": f"inlet {', '.join(spoofed)} read up to {-worst:.1f} °C cooler than their PDU power and "
                                   f"the supply air allow",
                         "action": "Treat the readings as forged: isolate the BMS network segment, check the sensors on site"})
    replay = replay_matches(frame, at)
    if replay:
        findings.append({"code": "REPLAYED_READINGS", "severity": "critical", "racks": [], "value": len(replay), "unit": "readings",
                         "limit": 0, "detail": f"{len(replay)} recent reading(s) exactly equal earlier ones, e.g. "
                                               f"{replay[0]['reading']} = {replay[0]['same_as']}",
                         "action": "Recorded data is being played back: isolate the network path, check the logger"})
    return {"trusted": not findings, "findings": findings,
            "residual_now_c": {r: (None if pd.isna(v) else round(float(v), 2)) for r, v in now.items()},
            "min_residual_now_c": None if now.isna().all() else round(float(now.min()), 2),
            "limits_c": {"single": SINGLE_LIMIT_C, "repeat": REPEAT_LIMIT_C}, "replay_matches": replay[:4],
            "model": {"inputs": "supply air (BMS) + rack PDU power (SNMP), now and 3 lags",
                      "residual_std_c": round(float(np.mean(list(model.residual_std.values()))), 3)}}


class IntegrityMonitor:
    """The same two checks, one reading at a time, inside the closed-loop AI controller (stateful)."""

    HOLD_STEPS = 4               # stay untrusted for 1 hour after the last flag

    def __init__(self, model: IntegrityModel):
        self.model = model
        self.reset()

    def reset(self):
        self.supply = deque(maxlen=LAGS)
        self.power = {r: deque(maxlen=LAGS) for r in C.RACKS}
        self.previous = {r: 0.0 for r in C.RACKS}
        self.seen, self.order = set(), deque()
        self.hold = 0

    def check(self, reading: dict) -> dict:
        self.supply.appendleft(reading["supply_air_c"])
        for r in C.RACKS:
            self.power[r].appendleft(reading.get(f"pdu_{r}_kw", np.nan))
        codes, worst = [], np.nan
        if len(self.supply) == LAGS:
            for r in C.RACKS:
                inlet = reading[f"inlet_{r}_c"]
                lags = np.array(self.power[r], dtype=float)
                if not np.isfinite(inlet) or not np.isfinite(lags).all() or not np.isfinite(list(self.supply)).all():
                    self.previous[r] = 0.0
                    continue
                res = inlet - self.model.predict_one(r, np.array(self.supply, float), lags)
                worst = res if not np.isfinite(worst) else min(worst, res)
                if res < SINGLE_LIMIT_C or (res < REPEAT_LIMIT_C and self.previous[r] < REPEAT_LIMIT_C):
                    codes.append(f"SPOOFED_READING:{r}")
                self.previous[r] = res
        key = _inlet_key([reading[c] for c in C.INLET_COLS])
        if key is not None:
            if key in self.seen:
                codes.append("REPLAYED_READINGS")
            else:
                self.seen.add(key)
                self.order.append(key)
                if len(self.order) > REPLAY_LOOKBACK:
                    self.seen.discard(self.order.popleft())
        self.hold = self.HOLD_STEPS if codes else max(0, self.hold - 1)
        return {"trusted": not codes and self.hold == 0, "codes": codes, "min_residual_c": worst}
