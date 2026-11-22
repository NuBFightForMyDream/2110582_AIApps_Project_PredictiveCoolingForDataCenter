"""6 · Results: energy and overheating, three controllers on the same weeks."""
import pandas as pd
import streamlit as st
from plotly.subplots import make_subplots

from predictive_cooling import config as C
from ui.common import B, CTRL, HEAD, LOGS, NAMES, SC, limit_line, moment, page_header, show, signed, style


page_header("Results", ":material/bolt:", "Did it save energy, without overheating?",
            ["Three controllers run the same simulated weeks: **fixed** setpoint, a tuned **rule**, and the **AI**.",
             "Green = fixed, orange = rule, blue = AI. Lower energy is better; minutes above 27 °C must stay at 0."], art="results")
ai = HEAD["ai"]
k = st.columns(5)
for col, label, value, note, icon, hlp in [
    (k[0], "Cooling energy", signed(-HEAD['rule']['cooling_pct']), "vs tuned rule", ":material/eco:",
     "AI vs the tuned rule-based controller, two test weeks, normal operation"),
    (k[1], "Cooling energy", signed(-HEAD['fixed']['cooling_pct']), f"vs fixed {B['fixed_sp']:.0f} °C", ":material/eco:",
     "AI vs the fixed setpoint, two test weeks, normal operation"),
    (k[2], "Whole facility", signed(-HEAD['rule']['facility_pct'], 2), f"≈ {HEAD['rule']['yearly_thb'] / 1000:,.0f}k THB / year",
     ":material/savings:", f"vs tuned rule. Includes the AI server ({C.AI_SERVER_KW:g} kW, 24/7). {C.ELECTRICITY_THB_PER_KWH:g} THB/kWh."),
    (k[3], "Minutes > 27 °C", f"{ai['violation_minutes']:.0f}", f"hottest {ai['hottest_inlet_c']:.1f} °C", ":material/shield:",
     "Minutes any rack inlet was above the 27 °C limit with the AI in control"),
    (k[4], "Decision time", f"{ai['decision_ms_mean']:.0f} ms", "target < 10 s", ":material/speed:", None),
]:
    col.metric(label, value, note, delta_color="off", delta_arrow="off", help=hlp, border=True, icon=icon)
pick = st.segmented_control("Scenario", list(SC), default="normal", format_func=lambda s: SC[s].title, key="res_sc") or "normal"
table = B["summary"].set_index(["scenario", "key"]).loc[pick].loc[["fixed", "rule", "ai"]]
hours = len(LOGS[pick, "ai"]) * C.DT_H
c1, c2 = st.columns([1.2, 1])
with c1:
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Cooling energy (kWh)", "Minutes above 27 °C"), horizontal_spacing=0.18)
    names = [NAMES[k] for k in table.index]
    fig.add_bar(y=names, x=table["cooling_kwh"], orientation="h", marker_color=[CTRL[k] for k in table.index], width=0.5,
                text=[f"{v:,.0f}" for v in table["cooling_kwh"]], textposition="outside", cliponaxis=False, row=1, col=1)
    fig.add_bar(y=names, x=table["violation_minutes"], orientation="h", marker_color=[CTRL[k] for k in table.index], width=0.5,
                text=[f"{v:,.0f}" for v in table["violation_minutes"]], textposition="outside", cliponaxis=False, row=1, col=2)
    fig.update_xaxes(range=[0, table["cooling_kwh"].max() * 1.25], row=1, col=1)
    fig.update_xaxes(range=[0, max(60, table["violation_minutes"].max() * 1.3)], row=1, col=2)
    fig.update_yaxes(autorange="reversed")
    fig.update_yaxes(showticklabels=False, row=1, col=2)
    show(style(fig, height=250, legend=False, hover="closest"))
    st.caption(f"Over {hours / 24:.0f} days. Savings look small on a zero-based axis because most cooling energy is needed "
               "whatever the setpoint; the AI only trims the part the setpoint can influence.")
with c2:
    avg = pd.DataFrame({NAMES[k]: [table.loc[k, "it_kwh"] / hours, table.loc[k, "cooling_kwh"] / hours,
                                   (table.loc[k, "other_kwh"] + table.loc[k, "ai_overhead_kwh"]) / hours,
                                   table.loc[k, "facility_kwh"] / hours, table.loc[k, "pue"]] for k in table.index},
                       index=["IT (kW)", "Cooling (kW)", "Other incl. AI server (kW)", "Total (kW)", "PUE"])
    st.markdown("**Average power, like proposal §8.4**")
    st.dataframe(avg.style.format("{:.3f}", subset=pd.IndexSlice[["PUE"], :]).format("{:.1f}", subset=pd.IndexSlice[avg.index[:-1], :]),
                 width="stretch")
if pick == "normal":
    f, r = HEAD["fixed"], HEAD["rule"]
    st.markdown(
        f"**Normal operation, 14 test days.** Compared with the tuned rule-based controller the AI uses "
        f"**{r['cooling_pct']:.1f} % less cooling energy** and **{r['facility_pct']:.2f} % less total energy** "
        f"(≈ {r['yearly_kwh']:,.0f} kWh ≈ {r['yearly_thb']:,.0f} THB per year). Against the fixed {B['fixed_sp']:.0f} °C setpoint: "
        f"**{f['cooling_pct']:.1f} %** cooling, **{f['facility_pct']:.2f} %** total (≈ {f['yearly_thb']:,.0f} THB per year). "
        f"Zero minutes above 27 °C for every controller.")
    st.warning("Honest reading: the proposal targeted ≥ 10 % cooling savings vs a tuned rule. In this mock room the AI gets "
               f"{r['cooling_pct']:.1f} %. Why: (1) rack B6 is a hot spot that caps how warm the room can run; (2) above 26 °C "
               "inlet the server fans speed up, so warmer is not always cheaper — the model knows this and stops; "
               "(3) the setpoint is the only knob. Fixing the B6 airflow or adding knobs (chilled-water temperature, fan "
               "speed) are the next levers.")
d = moment().date()                            # the day picked in the sidebar
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09,
                    subplot_titles=("Setpoint (°C)", "True hottest inlet (°C)"))
for key in ["fixed", "rule", "ai"]:
    part = LOGS[pick, key].loc[str(d)]
    fig.add_scatter(x=part.index, y=part["setpoint_in_use"], name=NAMES[key], line=dict(color=CTRL[key], width=2, shape="hv"), row=1, col=1)
    fig.add_scatter(x=part.index, y=part["max_inlet_c"], name=NAMES[key], showlegend=False, line=dict(color=CTRL[key], width=2), row=2, col=1)
limit_line(fig, 2, 1)
show(style(fig, height=470, title=f"{pd.Timestamp(d):%a %d %b}, three controllers: the AI rides closer to the limit, but not over it"))
with st.expander("All scenarios, all numbers", icon=":material/table_chart:"):
    cols = ["scenario", "controller", "facility_kwh", "cooling_kwh", "it_kwh", "pue", "violation_minutes", "hottest_inlet_c",
            "mean_setpoint_c", "setpoint_changes", "fallback_steps", "emergency_steps", "integrity_steps", "decision_ms_mean"]
    st.dataframe(B["summary"][cols].round(2), hide_index=True, width="stretch")
    st.markdown(f"Baselines were tuned on the validation weeks: fixed = highest setpoint with no overheating "
                f"(**{B['fixed_sp']:.0f} °C**); rule-based = lowest-energy safe deadband ({B['rule_text']}).")
