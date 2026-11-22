"""Upgrades: each hardware option measured in closed loop together with the AI, ranked by payback."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from predictive_cooling import config as C
from predictive_cooling.hardware import advisor as hw_advisor
from predictive_cooling.hardware.catalog import GRID_EMISSION_T_PER_MWH
from predictive_cooling.hardware.upgrades import UPGRADES
from ui.common import B, CTRL, diagram, hardware_state, how_it_works, kpi, kpi_row, moment, page_header, show, style
from ui.panels import upgrade_frame

page_header("Upgrades", ":material/construction:", "Which hardware upgrade pays back? Each option ran in closed loop on the upgraded "
            "room, with the old rule-based controller and with the AI, so the savings are measured, not quoted.", art="upgrades")
study = B["upgrades"]
base = hw_advisor.plan(study)["baseline"]                        # today's AI on today's room
kpi_row(kpi("Facility today", f"{base['facility_kwh_yr'] / 1000:,.0f}", "MWh per year"),
        kpi("Cooling today", f"{base['cooling_kwh_yr'] / 1000:,.0f}", "MWh per year"),
        kpi("PUE today", f"{base['pue']:.3f}", "today's AI"))
with how_it_works("Use your own prices", icon=":material/edit:"):
    capex_frame = pd.DataFrame([{"Option": u.title, "Budget low (THB)": u.capex_thb[0], "Budget high (THB)": u.capex_thb[1],
                                 "CAPEX used (THB)": sum(u.capex_thb) / 2} for u in UPGRADES.values()], index=list(UPGRADES))
    edited = st.data_editor(capex_frame, hide_index=True, width="stretch", key="dc_capex",
                            disabled=["Option", "Budget low (THB)", "Budget high (THB)"],
                            column_config={"CAPEX used (THB)": st.column_config.NumberColumn(min_value=0, step=50_000, format="%d")})
    st.caption("Budget assumptions for this 12-rack room, not quotes. Change the last column; payback and ranking update.")
advice = hw_advisor.plan(study, hardware_state(str(moment()))[1], dict(zip(UPGRADES, edited["CAPEX used (THB)"].astype(float))))
quick, biggest = advice["options"][0], max(advice["options"], key=lambda o: o["saved_kwh_yr"])
with st.container(horizontal=True):
    for icon, head, o in ((":material/bolt:", "Pays back fastest", quick), (":material/trending_down:", "Saves the most", biggest)):
        with st.container(border=True):
            st.markdown(f"{icon} **{head}** · {o['title']}")
            st.markdown(f"**{o['saved_facility_pct']:.1f} %** of facility energy · {o['saved_thb_yr']:,.0f} THB and "
                        f"{o['saved_tco2_yr']:g} tCO₂ a year · payback **{o['payback_years']:g} years**")
if advice["maintenance_first"]:
    st.markdown(f"**Do first** (from the equipment findings at {moment():%a %d %b %H:%M}): "
                + "; ".join(f"{m['device']}: {m['action'].split(':')[0].lower()} (≈ {m['budget_thb']:,.0f} THB)"
                            for m in advice["maintenance_first"]))
opts = sorted(advice["options"], key=lambda o: o["saved_facility_pct"])
fig = go.Figure()
fig.add_bar(y=[o["title"] for o in opts], x=[o["hardware_only_facility_pct"] for o in opts], orientation="h",
            name="Hardware + rule-based controller", marker_color=CTRL["rule"], width=0.36)
fig.add_bar(y=[o["title"] for o in opts], x=[o["saved_facility_pct"] for o in opts], orientation="h",
            name="Hardware + AI", marker_color=CTRL["ai"], width=0.36,
            text=[f"{o['saved_facility_pct']:.1f} % · payback {o['payback_years']:g} yr" for o in opts], textposition="outside",
            cliponaxis=False)
fig.update_layout(barmode="group")
fig.update_xaxes(title="facility energy saved vs today (%)", range=[0, max(o["saved_facility_pct"] for o in opts) * 1.45])
show(style(fig, height=380, title="What each upgrade saves, with and without the AI", hover="closest"))

with how_it_works("All numbers and how each option is tested", icon=":material/table_chart:"):
    st.dataframe(upgrade_frame(advice), hide_index=True, width="stretch",
                 column_config={"Saves kWh/yr": st.column_config.NumberColumn(format="%d"),
                                "THB/yr": st.column_config.NumberColumn(format="%d"),
                                "CAPEX THB": st.column_config.NumberColumn(format="%d")})
    diagram("""
flowchart LR
    U["Upgrade option"]:::step --> P["Plant model with the<br/>physical change"]:::step
    P --> R["Rule-based controller<br/>(hardware alone)"]:::step
    P --> H["Simulate 13 weeks →<br/>retrain the AI"]:::ai --> N["AI on the new room<br/>(physical + AI)"]:::ai
    R --> E["2 test weeks → kWh,<br/>minutes > 27 °C → per year"]:::ok
    N --> E
""", alt="Each option changes the plant model and runs with the rule-based controller and with the retrained AI")
    st.caption("  \n".join(advice["notes"]) + f"  \nCO₂: Thailand grid factor {GRID_EMISSION_T_PER_MWH} tCO₂/MWh (TGO, 2022); "
               f"electricity {C.ELECTRICITY_THB_PER_KWH:g} THB/kWh. The agents give the same plan with the task *Plan upgrades*.")
