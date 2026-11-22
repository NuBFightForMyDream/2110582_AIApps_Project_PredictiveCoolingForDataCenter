"""Panels and tables shared by several pages (hardware findings, upgrade plan)."""
import pandas as pd
import streamlit as st
from predictive_cooling.hardware.diagnostics import summary_note

SEVERITY_BADGE = {"ok": ("OK", "green"), "watch": ("Watch", "blue"), "warning": ("Warning", "orange"),
                  "critical": ("Critical", "red")}
CONSTRAINT_TEXT = {"none": "None — the AI may run warmer", "no_raise": "No warmer than now",
                   "fallback": "No warmer than now or than fallback"}


def findings_frame(diag):
    rows = [{"Severity": SEVERITY_BADGE[f["severity"]][0], "Device": f["device"], "Finding": f["code"],
             "What": f["label"], "Now": None if f["value"] is None else f"{f['value']:g} {f['unit']}".strip(),
             "Limit": None if f["limit"] is None else f"{f['limit']:g}",
             "Next limit": None if f["days_to_next"] is None else f"{f['next_severity']} {f['next_limit']:g} in ~{f['days_to_next']:g} d",
             "Constraint": f["constraint"], "Action": f["action"], "Basis": f["basis"]} for f in diag["findings"]]
    return pd.DataFrame(rows, columns=["Severity", "Device", "Finding", "What", "Now", "Limit", "Next limit", "Constraint",
                                       "Action", "Basis"])


def hardware_panel(diag):
    """The Hardware Engineer's report inside an agent case."""
    with st.container(border=True):
        label, color = SEVERITY_BADGE[diag["overall"]]
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(":material/memory: **Hardware Engineer's report** (re-checked by G3)")
            st.badge(label, color=color)
            st.badge(f"Constraint: {CONSTRAINT_TEXT[diag['constraint']]}", color="gray" if diag["constraint"] == "none" else "orange",
                     icon=":material/lock:" if diag["constraint"] != "none" else ":material/lock_open:")
        st.caption(summary_note(diag))
        if diag["findings"]:
            st.dataframe(findings_frame(diag)[["Severity", "Device", "Finding", "Now", "Limit", "Next limit", "Constraint", "Action"]],
                         hide_index=True, width="stretch")



def upgrade_frame(advice):
    return pd.DataFrame([{
        "Option": o["title"], "Example products": " / ".join(o["products"]), "Saves kWh/yr": o["saved_kwh_yr"],
        "THB/yr": o["saved_thb_yr"], "tCO₂/yr": o["saved_tco2_yr"], "Cooling −%": o["saved_cooling_pct"],
        "Facility −%": o["saved_facility_pct"], "CAPEX THB": o["capex_thb"], "Payback (yr)": o["payback_years"],
        "Min > 27 °C": o["minutes_over_27c"], "Run with": o["variant"]} for o in advice["options"]])
