"""Upgrade advisor: each hardware option measured in closed loop together with the AI, ranked by payback."""
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from predictive_cooling import config as C
from predictive_cooling.hardware import advisor as hw_advisor
from predictive_cooling.hardware.catalog import GRID_EMISSION_SOURCE, GRID_EMISSION_T_PER_MWH
from predictive_cooling.hardware.upgrades import UPGRADES
from ui.common import B, CTRL, diagram, hardware_state, how_it_works, kpi, kpi_row, moment, page_header, show, style
from ui.panels import upgrade_frame


page_header("Upgrade advisor", ":material/construction:", "Which hardware upgrade pays back, and how much does the AI add on top?",
            ["Each option changes the plant model (conservatively against the vendor claims) and runs the two test weeks on the "
             "upgraded room: with the rule-based controller (**hardware alone**) and with the AI, retrained for the new room "
             "where it matters (**physical + AI**).",
             "Savings are measured by the simulated plant, annualised, then ranked by payback. Maintenance the equipment "
             "findings call for comes first.",
             "Put your own quotes in the CAPEX column: the ranking updates."], art="upgrades")
with how_it_works("How each option is tested"):
    diagram("""
flowchart LR
    U["Upgrade option<br/>e.g. EC fans"]:::step --> P["Plant model with the<br/>physical change"]:::step
    P --> R["Rule-based controller<br/>(hardware alone)"]:::step
    P --> A["Today's AI"]:::ai
    P --> H["Simulate 13 weeks →<br/>retrain the forecaster"]:::ai --> N["Retrained AI<br/>(physical + AI)"]:::ai
    R --> E["2 test weeks: kWh,<br/>minutes > 27 °C"]:::ok
    A --> E
    N --> E
    E --> Y["Annualise: kWh, THB,<br/>tCO₂, payback"]:::ok
""", alt="Each upgrade option changes the plant model, runs with the rule-based controller, today's AI and a retrained AI, then annualised savings and payback")
    st.caption("Compared with today's AI on today's room. Electricity 4 THB/kWh. After any physical change the sensor-integrity "
               "model must be re-baselined, so the study runs without it.")
dc_at = moment()
study = B["upgrades"]
capex_frame = pd.DataFrame([{"Option": u.title, "Budget low (THB)": u.capex_thb[0], "Budget high (THB)": u.capex_thb[1],
                             "CAPEX used (THB)": sum(u.capex_thb) / 2} for u in UPGRADES.values()], index=list(UPGRADES))
base = hw_advisor.plan(study)["baseline"]                        # today's AI on today's room (no CAPEX needed)
kpi_row(kpi("Facility today", f"{base['facility_kwh_yr'] / 1000:,.0f}", "MWh per year"),
        kpi("Cooling today", f"{base['cooling_kwh_yr'] / 1000:,.0f}", "MWh per year"),
        kpi("PUE today", f"{base['pue']:.3f}", "today's AI"))
c1, c2 = st.columns([1.6, 1], vertical_alignment="center")
with c1:
    st.caption("CAPEX are budget assumptions for this 12-rack room. Put your own quotes in the last column; "
                "savings, payback and the ranking update.")
    edited = st.data_editor(capex_frame, hide_index=True, width="stretch", key="dc_capex",
                            disabled=["Option", "Budget low (THB)", "Budget high (THB)"],
                            column_config={"CAPEX used (THB)": st.column_config.NumberColumn(min_value=0, step=50_000, format="%d")})
capex = dict(zip(UPGRADES, edited["CAPEX used (THB)"].astype(float)))
diag_now = hardware_state(str(dc_at))[1]                         # findings at the sidebar moment
advice = hw_advisor.plan(study, diag_now, capex)
with c2:
    quick = advice["options"][0]
    with st.container(border=True):
        st.markdown(f":material/bolt: **Fastest payback** · {quick['title']}")
        st.markdown(f"**{quick['payback_years']:g} years** · {quick['saved_thb_yr']:,.0f} THB a year · "
                    f"{quick['saved_tco2_yr']:g} tCO₂ a year")
st.dataframe(upgrade_frame(advice), hide_index=True, width="stretch",
             column_config={"Saves kWh/yr": st.column_config.NumberColumn(format="%d"),
                            "THB/yr": st.column_config.NumberColumn(format="%d"),
                            "CAPEX THB": st.column_config.NumberColumn(format="%d")})
opts = sorted(advice["options"], key=lambda o: o["saved_facility_pct"])
fig = go.Figure()
fig.add_bar(y=[o["title"] for o in opts], x=[o["hardware_only_facility_pct"] for o in opts], orientation="h",
            name="Hardware + rule-based controller", marker_color=CTRL["rule"], width=0.36)
fig.add_bar(y=[o["title"] for o in opts], x=[o["saved_facility_pct"] for o in opts], orientation="h",
            name="Hardware + AI (retrained where it matters)", marker_color=CTRL["ai"], width=0.36,
            text=[f"{o['saved_facility_pct']:.1f} % · {o['saved_tco2_yr']:g} tCO₂/yr" for o in opts], textposition="outside",
            cliponaxis=False)
fig.update_layout(barmode="group")
fig.update_xaxes(title="facility energy saved vs today's AI on today's room (%)", range=[0, max(o["saved_facility_pct"] for o in opts) * 1.35])
show(style(fig, height=380, title="What each upgrade saves, with and without the AI", hover="closest"))
if advice["maintenance_first"]:
    st.markdown(f"**Maintenance first**, from the equipment findings at {dc_at:%a %d %b %H:%M}:")
    st.markdown("\n".join(f"- **{m['device']}** · {m['action']} (≈ {m['budget_thb']:,.0f} THB)" for m in advice["maintenance_first"]))
st.info("  \n".join(advice["notes"]) + f"  \nCO₂ uses Thailand's grid factor {GRID_EMISSION_T_PER_MWH} tCO₂/MWh (TGO, 2022). "
        f"Electricity {C.ELECTRICITY_THB_PER_KWH:g} THB/kWh.", icon=":material/info:")
st.caption(f"Grid factor source: {GRID_EMISSION_SOURCE}. Ask the agents with the task *Plan upgrades* to get the same plan "
           "through the Hardware Engineer (skill S8), recomputed by G3.")
