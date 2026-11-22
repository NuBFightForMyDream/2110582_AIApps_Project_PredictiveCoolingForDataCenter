"""Step 5 — safety filter between the AI and the cooling equipment.

The MPC only *proposes*. Before a setpoint is sent, these rules are checked in order:

R1 Missing data   any rack sensor is missing -> ignore the AI, use the fallback setpoint
R2 Unfamiliar     sensors far outside the training data -> ignore the AI, use the fallback setpoint
R6 Untrusted      the sensor data failed the integrity check (forged or replayed readings, unauthorised
                  setpoint write) -> never warmer than now or than the fallback setpoint
R5 Hardware       the Hardware Engineer's constraint: "no_raise" -> never warmer than now,
                  "fallback" -> never warmer than now or than the fallback setpoint (a colder AI
                  proposal is kept). Agent cases only; the closed-loop study passes no constraint.
R3 Too hot now    measured hottest inlet within 0.3 °C of the limit -> cool by 2 °C now
R4 Limits         keep the setpoint in 16-24 °C; normal changes at most 1 °C per 15 minutes

The fallback setpoint is the operator's proven fixed setting (the "Fixed setpoint" baseline),
so losing the AI simply returns the room to how it was run before.
"""
import math

from . import config as C

RULES = {
    "R1_missing_data": "Missing sensor data → fallback setpoint",
    "R2_unfamiliar_conditions": "Conditions outside training data → fallback setpoint",
    "R3_too_hot_now": "Measured inlet near limit → cool by 2 °C now",
    "R4_rate_or_range_limit": "Change limited to ±1 °C per step / 16-24 °C",
    "R5_equipment_constraint": "Hardware fault → never warmer than now (and than fallback if a unit failed)",
    "R6_untrusted_data": "Sensor data failed the integrity check → never warmer than now, toward fallback",
}
EQUIPMENT_CONSTRAINTS = ("none", "no_raise", "fallback")


class SafetyFilter:
    def __init__(self, fallback_sp: float, limit=C.INLET_LIMIT, emergency_margin=C.EMERGENCY_MARGIN):
        self.fallback_sp = fallback_sp
        self.limit = limit
        self.emergency_margin = emergency_margin

    def check(self, proposed_sp, current_sp, reading, unfamiliar=(), equipment="none", trusted=True):
        """Return (setpoint to send, list of rule ids that fired).

        `equipment` is the Hardware Engineer's constraint (R5); `trusted` is the integrity verdict (R6)."""
        if equipment not in EQUIPMENT_CONSTRAINTS:
            raise ValueError(f"unknown equipment constraint {equipment!r}")
        fired = []
        target = proposed_sp
        inlets = [reading[c] for c in C.INLET_COLS]
        if any(v is None or math.isnan(v) for v in inlets):
            fired.append("R1_missing_data")
            target = self.fallback_sp
        elif unfamiliar:
            fired.append("R2_unfamiliar_conditions")
            target = self.fallback_sp
        if not trusted:                              # forged data could hide a hot room: never warm it up
            fired.append("R6_untrusted_data")
            target = min(target, self.fallback_sp, current_sp)
        if equipment == "fallback":                  # cooling hardware failed: never warm the room up
            fired.append("R5_equipment_constraint")
            target = min(target, self.fallback_sp, current_sp)
        elif equipment == "no_raise" and target > current_sp:
            fired.append("R5_equipment_constraint")
            target = current_sp
        hottest = max((v for v in inlets if v is not None and not math.isnan(v)), default=math.nan)
        fastest_drop = 1.0
        if hottest >= self.limit - self.emergency_margin:
            fired.append("R3_too_hot_now")
            target = min(target, current_sp - 2)
            fastest_drop = 2.0
        limited = min(max(target, current_sp - fastest_drop), current_sp + 1)
        limited = min(max(limited, C.SP_MIN), C.SP_MAX)
        if limited != target:
            fired.append("R4_rate_or_range_limit")
        return float(limited), fired
