"""Hardware diagnostics: what is wrong with the equipment, how soon it matters, and what it means for cooling.

Three kinds of check, all plain Python on the gateway poll (now) and the historian (the last 7 days):
1. Limits per point, each with the standard or datasheet figure it comes from.
2. Trends: a straight line through the daily means projects the days until the next limit
   (predictive maintenance). Only a consistent trend (r² ≥ 0.8 over ≥ 3 days) is projected.
3. Capacity: can the CRAH units still carry the week's peak IT load if one of them fails (N+1)?

Every finding carries a cooling constraint, which the Supervisor passes on and safety rule R5 enforces:
    none      advisory only (power, humidity, sensor health)
    no_raise  a cooling-path warning: do not run the room warmer than now
    fallback  a cooling-path failure with no backup: return to the proven fallback setpoint
"""
from dataclasses import dataclass, field
import math

import numpy as np
import pandas as pd

from ..security.attacks import apply_equipment_attack
from .gateway import Gateway, SimulatedFieldBus
from .registry import CRAH_RATED_AIRFLOW_M3H, CRAH_RATED_KW, DEVICES, REGISTRY
from .telemetry import dew_point, rh_from_dew_point

SEVERITY = ("ok", "watch", "warning", "critical")
CONSTRAINTS = ("none", "no_raise", "fallback")
PROJECT_DAYS = 7                 # a limit projected within a week makes a point "watch"
TRIP_MINUTES = 30                # demo: a tripped device has been down for the last 30 minutes


@dataclass(frozen=True)
class Rule:
    code: str
    applies_to: str              # device kind, or "env_ca" / "env_dp" for the two room-sensor types
    metric: str
    label: str
    unit: str
    watch: float | None
    warning: float
    critical: float | None
    basis: str
    action: str
    cooling: bool                # a problem here reduces cooling capacity
    higher_is_worse: bool = True


RULES = [
    Rule("FILTER_LOADING", "crah", "filter_dp_100_pa", "Filter pressure drop (normalised to 100 % fan)", "Pa", 200, 250, 350,
         "Panel-filter final pressure drop ≈ 250 Pa (filter datasheet); measured ΔP ÷ (fan speed)² so fan changes do not hide it",
         "Replace the CRAH filter", cooling=True),
    Rule("CONDENSER_FOULING", "chiller", "cond_approach_c", "Condenser approach", "°C", 2.0, 3.0, 5.0,
         "Design approach ≈ 1 °C; > 3 °C means fouled tubes (rule of thumb: ≈ 3 % more compressor power per °C)",
         "Clean the condenser tubes and check the water treatment", cooling=True),
    Rule("BEARING_WEAR", "pump", "vibration_mm_s", "Vibration velocity (RMS)", "mm/s", 1.12, 1.8, 4.5,
         "ISO 10816-1 class I machines: zone C > 1.8 mm/s (not for long-term running), zone D > 4.5 mm/s (damage)",
         "Switch duty to the standby pump and replace the bearing", cooling=True),
    Rule("BEARING_OVERHEAT", "pump", "bearing_temp_c", "Bearing temperature", "°C", None, 70.0, 85.0,
         "Rolling-element bearings: alarm ≈ 70 °C, trip ≈ 85 °C (motor maker guidance)",
         "Check lubrication and alignment", cooling=True),
    Rule("TOWER_APPROACH", "cooling_tower", "approach_c", "Tower approach", "°C", 5.5, 6.5, 8.0,
         "Design approach ≈ 4 °C; a rising approach means fouled fill, blocked nozzles or a weak fan",
         "Inspect fill, nozzles and fan", cooling=True),
    Rule("UPS_BATTERY_HOT", "ups", "battery_temp_c", "Battery temperature", "°C", 27.0, 30.0, 35.0,
         "VRLA battery life roughly halves for every 8–10 °C above 25 °C", "Check the battery-room cooling", cooling=False),
    Rule("UPS_LOAD_HIGH", "ups", "load_pct", "UPS load", "%", 70.0, 80.0, 95.0,
         "Site limit 80 % keeps headroom for load steps and growth", "Plan UPS capacity or move load", cooling=False),
    Rule("ROOM_HUMIDITY", "env_ca", "rh_pct", "Cold-aisle relative humidity", "%RH", None, 60.0, 80.0,
         "ASHRAE TC 9.9: recommended ≤ 60 %RH (and dew point ≤ 15 °C); allowable class A1 ≤ 80 %RH",
         "Check the CRAH humidity control", cooling=False),
    Rule("SENSOR_DRIFT", "env_ca", "rh_deviation_pct", "Disagreement with the CRAH return-air dew point", "%RH", 3.5, 5.0, 10.0,
         "Independent humidity sensors should agree within about ±3 %RH (typical transmitter accuracy)",
         "Recalibrate or replace the sensor; ignore its humidity until then", cooling=False),
    Rule("CONTAINMENT_PRESSURE", "env_dp", "aisle_dp_pa", "Cold-aisle over-pressure", "Pa", 1.5, 1.0, 0.0,
         "A contained cold aisle stays slightly positive (≈ 1–5 Pa) so hot air cannot leak back in",
         "Check CRAH airflow, aisle doors and blanking panels", cooling=True, higher_is_worse=False),
]


def _kind(device):
    if device.kind == "env":
        return "env_dp" if device.id.startswith("ENV-DP") else "env_ca"
    return device.kind


def trip(frame: pd.DataFrame, device_id: str, at) -> pd.DataFrame:
    """Demo fault: `device_id` trips (stops, alarm) for the last 30 minutes before `at`."""
    at = pd.Timestamp(at)
    rows = (frame.index > at - pd.Timedelta(minutes=TRIP_MINUTES + 1)) & (frame.index <= at)
    dev = REGISTRY[device_id]
    zero = {"crah": ["status", "fan_speed_pct", "fan_kw", "airflow_m3h", "filter_dp_pa", "chw_valve_pct"],
            "chiller": ["status", "load_pct", "kw", "cop"], "pump": ["status", "speed_hz", "flow_m3h", "kw", "vibration_mm_s"],
            "cooling_tower": ["status", "fan_speed_pct", "kw"]}[dev.kind]
    for point in zero:
        frame.loc[rows, dev.column(point)] = 0.0
    if dev.kind == "chiller":
        frame.loc[rows, dev.column("chws_c")] = frame.loc[rows, dev.column("chwr_c")]     # no cooling: supply = return
    if dev.kind == "pump" and not dev.standby:                                           # the standby pump takes over
        standby = next(d for d in DEVICES if d.group == dev.group and d.standby)
        for point, value in {"status": 1.0, "speed_hz": 48.0, "flow_m3h": 24.0, "kw": 2.1, "vibration_mm_s": 0.8}.items():
            frame.loc[rows, standby.column(point)] = value
    return frame


@dataclass
class EquipmentWindow:
    """What the Hardware Engineer may see: the historian up to the case time and a live gateway poll at it."""
    telemetry: pd.DataFrame
    at: pd.Timestamp
    days: float = 7.0
    trips: tuple = ()
    attack: str = "none"                     # demo: "setpoint_tamper" writes CRAH-2's setpoint (security/attacks.py)
    frame: pd.DataFrame = field(init=False)
    snapshot: dict = field(init=False)

    def __post_init__(self):
        self.at = pd.Timestamp(self.at)
        frame = self.telemetry.loc[self.at - pd.Timedelta(days=self.days):self.at].copy()     # never after `at`
        for device_id in self.trips:
            frame = trip(frame, device_id, self.at)
        self.frame = apply_equipment_attack(frame, self.at, self.attack)
        self.gateway = Gateway(SimulatedFieldBus(frame))
        self.snapshot = self.gateway.poll_all(self.at)


# ---- metrics ---------------------------------------------------------------------------------
def _col(frame, device, point):
    return frame[device.column(point)].astype(float)


def _reference_dew_point(frame):
    """Room dew point from the CRAH return-air temperature + humidity (independent of the aisle sensors)."""
    dews = [dew_point(_col(frame, REGISTRY[c], "return_air_c"), _col(frame, REGISTRY[c], "return_rh_pct"))
            for c in ("CRAH-1", "CRAH-2")]
    return pd.concat(dews, axis=1).mean(axis=1)


def metrics(frame: pd.DataFrame, device) -> dict:
    """Derived series a rule looks at, per device."""
    kind = _kind(device)
    if kind == "crah":
        speed = _col(frame, device, "fan_speed_pct") / 100
        return {"filter_dp_100_pa": (_col(frame, device, "filter_dp_pa") / speed ** 2).where(speed > 0.05)}
    if kind == "env_ca":
        rh = _col(frame, device, "rh_pct")
        expected = rh_from_dew_point(_col(frame, device, "temp_c"), _reference_dew_point(frame))
        return {"rh_pct": rh, "rh_deviation_pct": (rh - expected).abs()}
    return {r.metric: _col(frame, device, r.metric) for r in RULES if r.applies_to == kind}


def trend(series: pd.Series, at, days=PROJECT_DAYS):
    """Slope of the daily means (units/day) over the last days, or None when there is no consistent trend."""
    s = series.dropna()
    if s.empty:
        return None
    age = (pd.Timestamp(at) - s.index) / pd.Timedelta(days=1)
    daily = s.groupby(np.floor(np.asarray(age, dtype=float))).mean()
    daily = daily[daily.index < days]
    if len(daily) < 3:
        return None
    x = -np.asarray(daily.index, dtype=float)
    y = daily.to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    total = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ((y - (slope * x + intercept)) ** 2).sum() / total if total > 0 else 0.0
    return float(slope) if r2 >= 0.8 else None


def _assess(rule: Rule, series: pd.Series, at):
    """(severity, value now, limit crossed, next severity, next limit, days until the next limit) or None."""
    value = series.dropna()
    value = float(value.iloc[-1]) if len(value) and value.index[-1] >= at - pd.Timedelta(minutes=30) else math.nan
    if math.isnan(value):
        return None
    worse = (lambda v, lim: v >= lim) if rule.higher_is_worse else (lambda v, lim: v <= lim)
    ladder = [("watch", rule.watch), ("warning", rule.warning), ("critical", rule.critical)]
    severity, crossed = "ok", None
    for name, limit in ladder:
        if limit is not None and worse(value, limit):
            severity, crossed = name, limit
    above = [(n, lim) for n, lim in ladder if lim is not None and not worse(value, lim) and n != "watch"]
    next_name, next_limit = above[0] if above else (None, None)
    slope, days = trend(series, at), None
    if next_limit is not None and slope:
        gap = (next_limit - value) if rule.higher_is_worse else (value - next_limit)
        speed = slope if rule.higher_is_worse else -slope
        if gap > 0 and speed > 0:
            days = round(gap / speed, 1)
    if severity == "ok" and days is not None and days <= PROJECT_DAYS:
        severity = "watch"                                           # not there yet, but heading there this week
    return severity, value, crossed, next_name, next_limit, days


def _standby_ready(device, snapshot):
    for other in DEVICES:
        if other.group == device.group and other.id != device.id and other.standby:
            reading = snapshot.get(other.id, {})
            if reading.get("comm") == "ok" and reading["values"].get("status") == 0:
                return True
    return False


def _constraint(cooling, severity, standby_ready=False):
    if not cooling or severity in ("ok", "watch"):
        return "none"
    if severity == "critical" and not standby_ready:
        return "fallback"
    return "no_raise"


def _finding(device, code, severity, constraint, label, value=None, unit="", limit=None, next_severity=None,
             next_limit=None, days=None, action="", basis=""):
    """`limit` is the threshold that was crossed; `days_to_next` projects when `next_limit` will be."""
    num = lambda x: None if x is None else round(float(x), 2)  # noqa: E731
    return {"device": device, "code": code, "severity": severity, "constraint": constraint, "label": label,
            "value": num(value), "unit": unit, "limit": num(limit), "next_severity": next_severity,
            "next_limit": num(next_limit), "days_to_next": days, "action": action, "basis": basis}


# ---- the diagnosis -----------------------------------------------------------------------------
CRAH_GROUP = "CRAH group"
ORDER = {s: i for i, s in enumerate(SEVERITY)}


def _comm_finding(device):
    severity = "warning" if device.cooling_path else "watch"
    return _finding(device.id, "COMM_LOSS", severity, _constraint(device.cooling_path, severity),
                    f"No answer over {device.protocol} ({device.endpoint})", action="Check the network path and the device controller",
                    basis="A cooling device that cannot be seen cannot be trusted to deliver capacity")


def _stopped_finding(device, status):
    """A duty unit with status 0. For the pump pair, the standby taking over is a warning, not a failure."""
    if device.kind == "pump":
        standby_on = any(status.get(d.id) == 1 for d in DEVICES if d.group == device.group and d.standby)
        code, severity = ("RUNNING_ON_STANDBY", "warning") if standby_on else ("NO_CHILLED_WATER_FLOW", "critical")
        label = ("Duty pump tripped; the standby pump is carrying the load with no backup left" if standby_on
                 else "Duty pump tripped and the standby pump did not start")
    else:
        code, severity, label = f"{device.kind.upper()}_TRIPPED", "critical", f"{device.name} has tripped"
    return _finding(device.id, code, severity, _constraint(True, severity), label,
                    action="Dispatch a technician; reset only after the cause is known",
                    basis="Unit status = 0 (stopped / alarm) for the last 30 minutes")


def _rule_findings(device, win):
    series = metrics(win.frame, device)
    out = []
    for rule in (r for r in RULES if r.applies_to == _kind(device)):
        result = _assess(rule, series[rule.metric], win.at)
        if result is None or result[0] == "ok":
            continue
        severity, value, crossed, next_name, next_limit, days = result
        constraint = _constraint(rule.cooling, severity, _standby_ready(device, win.snapshot))
        out.append(_finding(device.id, rule.code, severity, constraint, rule.label, value, rule.unit, crossed,
                            next_name, next_limit, days, rule.action, rule.basis))
    if any(f["code"] == "SENSOR_DRIFT" and f["severity"] != "watch" for f in out):
        out = [f for f in out if f["code"] != "ROOM_HUMIDITY"]        # a drifting sensor says nothing about the room
    return out


def _device_findings(device, win, status):
    reading = win.snapshot[device.id]
    if reading["comm"] != "ok":
        return [_comm_finding(device)]
    out = []
    bad = [p for p, q in reading["quality"].items() if q != "good"]
    if bad:
        out.append(_finding(device.id, "BAD_POINT", "watch", "none", "Points with bad quality: " + ", ".join(bad),
                            action="Check the transmitter and wiring", basis="Value outside the physical range"))
    if status.get(device.id, 1) != 1:                 # an idle standby unit is healthy; a stopped duty unit is not
        return out + ([] if device.standby else [_stopped_finding(device, status)])
    return out + _rule_findings(device, win)


def diagnose(win: EquipmentWindow) -> dict:
    snap = win.snapshot
    status = {d.id: snap[d.id]["values"].get("status") for d in DEVICES if any(p.name == "status" for p in d.points)}
    findings = [f for device in DEVICES for f in _device_findings(device, win, status)]
    capacity = crah_capacity(win)
    if capacity["finding"]:
        findings.append(capacity["finding"])
    del capacity["finding"]
    findings.sort(key=lambda f: (-ORDER[f["severity"]], f["constraint"] == "none", f["device"]))
    worst = {}
    for f in findings:
        if f["device"] in REGISTRY and ORDER[f["severity"]] > ORDER[worst.get(f["device"], "ok")]:
            worst[f["device"]] = f["severity"]
    constraint = max((f["constraint"] for f in findings), key=CONSTRAINTS.index, default="none")
    return {
        "case_time": f"{win.at:%Y-%m-%d %H:%M}", "devices_polled": len(snap),
        "devices_answering": sum(r["comm"] == "ok" for r in snap.values()),
        "overall": max((f["severity"] for f in findings), key=ORDER.get, default="ok"), "constraint": constraint,
        "constraint_reasons": [f"{f['device']} {f['code']}" for f in findings if f["constraint"] == constraint != "none"],
        "findings": findings, "capacity": capacity,
        "device_health": {d.id: worst.get(d.id, "ok") for d in DEVICES},
    }


def crah_capacity(win: EquipmentWindow) -> dict:
    """N+1 check: sensible capacity of each running CRAH (rated x measured airflow ratio) vs the week's peak IT load."""
    snap, frame = win.snapshot, win.frame
    units = {}
    for device in (d for d in DEVICES if d.kind == "crah"):
        values = snap[device.id]["values"]
        if snap[device.id]["comm"] != "ok" or values.get("status") != 1:
            units[device.id] = 0.0
            continue
        speed = (values.get("fan_speed_pct") or 0) / 100
        airflow = values.get("airflow_m3h")
        # an unreadable airflow point is reported as BAD_POINT; it must not look like a capacity loss
        ratio = airflow / (CRAH_RATED_AIRFLOW_M3H * speed) if speed > 0.05 and airflow is not None else 1.0
        units[device.id] = round(CRAH_RATED_KW * float(np.clip(ratio, 0.5, 1.0)), 1)
    pdu_cols = [d.column("power_kw") for d in DEVICES if d.kind == "pdu"]
    it_now = frame[pdu_cols].sum(axis=1, min_count=len(pdu_cols))
    if it_now.notna().sum() == 0:
        it_now = frame[REGISTRY["UPS-1"].column("output_kw")]
    peak = float(it_now.max())
    running = sum(units.values())
    n_minus_1 = running - max(units.values()) if sum(v > 0 for v in units.values()) >= 2 else 0.0
    out = {"unit_capacity_kw": units, "running_capacity_kw": round(running, 1), "n_minus_1_capacity_kw": round(n_minus_1, 1),
           "peak_it_kw_7d": round(peak, 1), "it_kw_now": round(float(it_now.dropna().iloc[-1]), 1) if it_now.notna().any() else None,
           "n_plus_1": bool(n_minus_1 >= peak), "finding": None}
    basis = "N+1: if any one CRAH fails, the others must still carry the highest IT load of the past week"
    if running < peak:
        out["finding"] = _finding(CRAH_GROUP, "CAPACITY_SHORTFALL", "critical", "fallback",
                                  "Running CRAH capacity is below the week's peak IT load", running, "kW", peak,
                                  action="Restore the failed unit; keep the room at the proven setpoint", basis=basis)
    elif n_minus_1 < peak:
        out["finding"] = _finding(CRAH_GROUP, "REDUNDANCY_LOST", "warning", "no_raise",
                                  "N+1 lost: one CRAH alone could not carry the week's peak IT load", n_minus_1, "kW", peak,
                                  action="Restore airflow on the weak unit (filter) before the next GPU batch", basis=basis)
    elif n_minus_1 < 1.05 * peak:
        out["finding"] = _finding(CRAH_GROUP, "REDUNDANCY_THIN", "watch", "none",
                                  "N+1 margin under 5 %", n_minus_1, "kW", peak,
                                  action="Watch the weaker unit's airflow", basis=basis)
    return out


def describe(f: dict) -> str:
    """One finding in words: 'CHWP-1 BEARING_WEAR (warning): 2.52 mm/s, limit 1.8; critical 4.5 in ~8.7 days'."""
    text = f"{f['device']} {f['code']} ({f['severity']})"
    if f["value"] is not None:
        text += f": {f['value']:g} {f['unit']}".rstrip()
        if f["limit"] is not None:
            text += f", limit {f['limit']:g}"
    if f["days_to_next"] is not None:
        text += f"; {f['next_severity']} {f['next_limit']:g} in ~{f['days_to_next']:g} days"
    return text


def summary_note(diag: dict) -> str:
    """Deterministic summary for the Supervisor (offline-mode note and the S5 statement)."""
    head = f"{diag['devices_answering']} of {diag['devices_polled']} devices answered"
    if diag["overall"] == "ok":
        cap = diag["capacity"]
        return (f"{head}; all equipment within limits, N+1 cooling capacity OK ({cap['n_minus_1_capacity_kw']:.0f} kW "
                f"vs week peak {cap['peak_it_kw_7d']:.0f} kW).")
    return f"{head}. " + "; ".join(describe(f) for f in diag["findings"][:3]) + f". Cooling constraint: {diag['constraint']}."
