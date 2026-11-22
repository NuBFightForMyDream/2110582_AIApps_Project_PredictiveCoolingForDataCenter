"""Upgrade advisor (skill S8 of the Hardware Engineer): what to fix first, and which upgrade pays back fastest.

Every number comes from the closed-loop upgrade study in the bundle (upgrades.py): the plant, not a vendor
brochure, says how much each option saves. CAPEX values are budget assumptions for a 12-rack room.
"""
import math

from .catalog import UPGRADE_PRODUCTS
from .upgrades import UPGRADES, economics

# Cheap maintenance that should come before any purchase: (action, budget THB)
MAINTENANCE = {
    "FILTER_LOADING": ("Replace the CRAH filter: restores airflow and N+1 capacity", 8_000),
    "REDUNDANCY_LOST": ("Restore the weak CRAH's airflow before the next GPU batch (usually the filter)", 8_000),
    "BEARING_WEAR": ("Switch duty to the standby pump and replace the bearing", 25_000),
    "BEARING_OVERHEAT": ("Check pump lubrication and alignment", 5_000),
    "CONDENSER_FOULING": ("Clean the chiller condenser tubes; check water treatment (≈ 3 % compressor power per °C approach)", 40_000),
    "SENSOR_DRIFT": ("Recalibrate or replace the humidity sensor", 3_000),
    "CONTAINMENT_PRESSURE": ("Close aisle doors, fit missing blanking panels", 5_000),
    "TOWER_APPROACH": ("Inspect tower fill, nozzles and fan", 15_000),
}
VARIANT_TEXT = {"rule": "rule-based controller", "ai": "today's AI", "ai_new": "AI retrained for the upgraded room"}


def _num(x, digits=2):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), digits)


def plan(study: dict, diag: dict | None = None, capex: dict | None = None) -> dict:
    econ = economics(study["table"], study["baseline"], study["days"], capex)
    options = []
    for key, upgrade in UPGRADES.items():
        rows = econ[econ["upgrade"] == key].set_index("variant")
        variant = "ai_new" if "ai_new" in rows.index else "ai"
        best, rule = rows.loc[variant], rows.loc["rule"]
        options.append({
            "key": key, "title": upgrade.title, "change": upgrade.change, "variant": VARIANT_TEXT[variant],
            "products": [f"{UPGRADE_PRODUCTS[p].vendor} · {UPGRADE_PRODUCTS[p].model}" for p in upgrade.products],
            "saved_kwh_yr": _num(best["saved_kwh_yr"], 0), "saved_thb_yr": _num(best["saved_thb_yr"], 0),
            "saved_tco2_yr": _num(best["saved_tco2_yr"], 1), "saved_cooling_pct": _num(best["saved_cooling_pct"]),
            "saved_facility_pct": _num(best["saved_facility_pct"]), "capex_thb": _num(best["capex_thb"], 0),
            "payback_years": _num(best["payback_years"], 1), "minutes_over_27c": int(best["violation_minutes"]),
            "mean_setpoint_c": _num(best["mean_setpoint_c"]), "at_setpoint_ceiling_pct": _num(best["at_ceiling_pct"], 0),
            "hardware_only_facility_pct": _num(rule["saved_facility_pct"]),
            "ai_adds_facility_pct": _num(best["saved_facility_pct"] - rule["saved_facility_pct"]), "note": upgrade.note,
        })
    options.sort(key=lambda o: (o["payback_years"] is None, o["payback_years"] or 0))
    maintenance = []
    for f in (diag or {}).get("findings", []):
        if f["code"] in MAINTENANCE and f["severity"] in ("watch", "warning", "critical"):
            action, cost = MAINTENANCE[f["code"]]
            maintenance.append({"device": f["device"], "code": f["code"], "severity": f["severity"], "action": action,
                                "budget_thb": cost, "days_to_next": f["days_to_next"]})
    notes = ["CAPEX values are budget assumptions for this 12-rack mock room, not quotes; savings are simulated over the two "
             "test weeks and annualised.",
             "After any physical change, re-baseline the sensor-integrity model: a contained room is cooler than the old "
             "physics expects and would look forged."]
    contained = next(o for o in options if o["key"] == "containment")
    if (contained["at_setpoint_ceiling_pct"] or 0) > 50:
        notes.append(f"With containment the AI sits at the 24 °C setpoint ceiling {contained['at_setpoint_ceiling_pct']:.0f} % of "
                     "the time: the racks would allow warmer, so the site's 16–24 °C policy becomes the limit.")
    baseline = study["baseline"]
    return {"basis": "closed-loop plant study, 2 test weeks annualised, vs today's AI on today's room",
            "baseline": {"facility_kwh_yr": _num(baseline["facility_kwh"] * 365 / study["days"], 0),
                         "cooling_kwh_yr": _num(baseline["cooling_kwh"] * 365 / study["days"], 0), "pue": _num(baseline["pue"], 3)},
            "options": options, "maintenance_first": maintenance, "notes": notes}


def summary_note(advice: dict) -> str:
    opts = advice["options"]
    quick = opts[0]
    biggest = max(opts, key=lambda o: o["saved_kwh_yr"] or 0)
    text = []
    if advice["maintenance_first"]:
        text.append("Maintenance first: " + "; ".join(f"{m['device']} — {m['action']}" for m in advice["maintenance_first"][:3]) + ".")
    text.append(f"Fastest payback: {quick['title']} ({quick['saved_thb_yr']:,.0f} THB/yr, payback {quick['payback_years']:g} years).")
    text.append(f"Largest saving: {biggest['title']} — {biggest['saved_facility_pct']:.1f} % of facility energy, "
                f"{biggest['saved_kwh_yr']:,.0f} kWh/yr ≈ {biggest['saved_thb_yr']:,.0f} THB and {biggest['saved_tco2_yr']:g} tCO₂ a "
                f"year, payback {biggest['payback_years']:g} years; hardware alone {biggest['hardware_only_facility_pct']:.1f} %, the "
                f"AI adds {biggest['ai_adds_facility_pct']:.2f} %.")
    text.append("No option let a rack exceed 27 °C." if all(o["minutes_over_27c"] == 0 for o in opts)
                else "Some options exceeded 27 °C in simulation; see the table.")
    return " ".join(text)
