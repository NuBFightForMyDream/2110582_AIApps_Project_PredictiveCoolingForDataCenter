"""Results: energy and overheating for three controllers on the same two test weeks, normal and with faults."""
import pandas as pd
import streamlit as st
from plotly.subplots import make_subplots

from predictive_cooling import config as C
from ui.common import (B, CTRL, HEAD, INK2, LOGS, NAMES, SC, how_it_works, kpi, kpi_row, limit_line, moment, page_header, show,
                       signed, style)

page_header("Results", ":material/bolt:", "Did it save energy without overheating? Three controllers run the same two test weeks "
            "the AI never trained on: a **fixed** setpoint (green), a tuned **rule** (orange) and the **AI** (blue).", art="results")
ai = HEAD["ai"]
kpi_row(kpi("Cooling energy", signed(-HEAD["rule"]["cooling_pct"]), "vs tuned rule", icon=":material/eco:"),
        kpi("Cooling energy", signed(-HEAD["fixed"]["cooling_pct"]), f"vs fixed {B['fixed_sp']:.0f} °C", icon=":material/eco:"),
        kpi("Whole facility", signed(-HEAD["rule"]["facility_pct"], 2), f"≈ {HEAD['rule']['yearly_thb'] / 1000:,.0f}k THB / year",
            icon=":material/savings:", help=f"vs tuned rule, incl. the AI server ({C.AI_SERVER_KW:g} kW, 24/7), "
                                            f"{C.ELECTRICITY_THB_PER_KWH:g} THB/kWh"),
        kpi("Minutes > 27 °C", f"{ai['violation_minutes']:.0f}", f"hottest {ai['hottest_inlet_c']:.1f} °C", icon=":material/shield:"))

pick = st.segmented_control("Scenario", list(SC), default="normal", format_func=lambda s: SC[s].title, key="res_sc") or "normal"
scen = SC[pick]
st.caption(scen.story)
keys = ["fixed", "rule", "ai"] + (["ai_unsafe"] if (pick, "ai_unsafe") in LOGS else [])
table = B["summary"].set_index(["scenario", "key"]).loc[pick].loc[keys]
fig = make_subplots(rows=1, cols=2, subplot_titles=("Cooling energy (kWh)", "Minutes above 27 °C"), horizontal_spacing=0.18)
names = [NAMES[k] for k in table.index]
colors = [CTRL[k] for k in table.index]
fig.add_bar(y=names, x=table["cooling_kwh"], orientation="h", marker_color=colors, width=0.5,
            text=[f"{v:,.0f}" for v in table["cooling_kwh"]], textposition="outside", cliponaxis=False, row=1, col=1)
fig.add_bar(y=names, x=table["violation_minutes"], orientation="h", marker_color=colors, width=0.5,
            text=[f"{v:,.0f}" for v in table["violation_minutes"]], textposition="outside", cliponaxis=False, row=1, col=2)
fig.update_xaxes(range=[0, table["cooling_kwh"].max() * 1.25], row=1, col=1)
fig.update_xaxes(range=[0, max(60, table["violation_minutes"].max() * 1.3)], row=1, col=2)
fig.update_yaxes(autorange="reversed")
fig.update_yaxes(showticklabels=False, row=1, col=2)
show(style(fig, height=230, legend=False, hover="closest"))

if pick == "normal":
    day = moment().date()
    lo, hi, title = pd.Timestamp(day), pd.Timestamp(day) + pd.Timedelta(hours=23, minutes=45), \
        f"{pd.Timestamp(day):%a %d %b}: the AI rides closer to the limit, but not over it"
else:
    center, hours = ((pd.Timestamp(scen.highlight[0][0]), scen.highlight[0][1]) if scen.highlight
                     else (LOGS[pick, "ai"]["max_inlet_c"].idxmax() - pd.Timedelta(hours=2), 2))
    lo, hi, title = center - pd.Timedelta(hours=5), center + pd.Timedelta(hours=hours + 5), f"Zoom on the first event · {center:%a %d %b}"
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09, subplot_titles=("True hottest inlet (°C)", "Setpoint sent (°C)"))
for key in keys:
    part = LOGS[pick, key].loc[lo:hi]
    dash = "dash" if key == "ai_unsafe" else None
    fig.add_scatter(x=part.index, y=part["max_inlet_c"], name=NAMES[key], line=dict(color=CTRL[key], width=2, dash=dash), row=1, col=1)
    fig.add_scatter(x=part.index, y=part["command"], name=NAMES[key], showlegend=False,
                    line=dict(color=CTRL[key], width=2, shape="hv", dash=dash), row=2, col=1)
for start, length in scen.highlight:
    s = pd.Timestamp(start)
    if lo <= s <= hi:
        fig.add_vrect(x0=s, x1=s + pd.Timedelta(hours=length), fillcolor="#f0efec", opacity=0.8, line_width=0, layer="below",
                      annotation_text="fault", annotation_position="top left", annotation_font=dict(size=11, color=INK2))
limit_line(fig, 1, 1)
show(style(fig, height=440, title=title))
TAKEAWAY = {
    "normal": f"The AI uses {HEAD['rule']['cooling_pct']:.1f} % less cooling energy than the tuned rule and "
              f"{HEAD['fixed']['cooling_pct']:.1f} % less than the fixed setpoint, with zero minutes above 27 °C. The target was "
              "10 %: rack B6 is a permanent hot spot, server fans speed up above 26 °C and the setpoint is the only knob. "
              "The Upgrades page measures the hardware levers.",
    "sensor_failure": "The rule-based controller trusts the remaining (cooler) sensors and lets B5/B6 overheat; so does the AI "
                      "without its safety filter. With the filter, missing data → fallback setpoint → no overheating.",
    "plant_change": "The room no longer matches the training data. The fixed setpoint that used to be safe now overheats for hours. "
                    "The AI notices its forecasts are too low and corrects itself; the short exceedances left are a cue to retrain.",
    "load_surge": "Nobody can forecast a job that never happened before. The AI runs closer to the limit, so it is hit harder in "
                  "the first 15 minutes; the 'too hot now' rule then cools by 2 °C at once.",
}
st.info(TAKEAWAY[pick], icon=":material/lightbulb:")

with how_it_works("All numbers", icon=":material/table_chart:"):
    hours = len(LOGS[pick, "ai"]) * C.DT_H
    avg = pd.DataFrame({NAMES[k]: [table.loc[k, "it_kwh"] / hours, table.loc[k, "cooling_kwh"] / hours,
                                   (table.loc[k, "other_kwh"] + table.loc[k, "ai_overhead_kwh"]) / hours,
                                   table.loc[k, "facility_kwh"] / hours, table.loc[k, "pue"]] for k in table.index},
                       index=["IT (kW)", "Cooling (kW)", "Other incl. AI server (kW)", "Total (kW)", "PUE"])
    st.markdown(f"**Average power, {SC[pick].title.lower()}** (like proposal §8.4)")
    st.dataframe(avg.style.format("{:.3f}", subset=pd.IndexSlice[["PUE"], :]).format("{:.1f}", subset=pd.IndexSlice[avg.index[:-1], :]),
                 width="stretch")
    cols = ["scenario", "controller", "facility_kwh", "cooling_kwh", "it_kwh", "pue", "violation_minutes", "hottest_inlet_c",
            "mean_setpoint_c", "setpoint_changes", "fallback_steps", "emergency_steps", "integrity_steps", "decision_ms_mean"]
    st.dataframe(B["summary"][cols].round(2), hide_index=True, width="stretch")
    st.caption(f"Baselines tuned on the validation weeks: fixed = highest setpoint with no overheating ({B['fixed_sp']:.0f} °C); "
               f"rule-based = lowest-energy safe deadband ({B['rule_text']}). AI decision time {ai['decision_ms_mean']:.0f} ms "
               "per step (target < 10 s).")
