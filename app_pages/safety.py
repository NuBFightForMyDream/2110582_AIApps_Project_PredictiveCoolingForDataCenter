"""5 · Safety: the rules between the AI and the equipment, and the fault scenarios."""
import pandas as pd
import streamlit as st
from plotly.subplots import make_subplots

from predictive_cooling.safety import RULES
from ui.common import B, CTRL, INK2, LOGS, NAMES, SC, diagram, how_it_works, limit_line, page_header, show, style


page_header("Safety", ":material/shield:", "What if something goes wrong? The AI only proposes; six rules can "
            "override it before anything is sent.",
            [f"When in doubt, fall back to the old proven setpoint (**{B['fixed_sp']:.0f} °C**) — never worse than before.",
             "**R5** listens to the Hardware Engineer: a cooling-equipment problem means *never run the room warmer*. "
             "**R6** does the same when the sensor data fails the integrity check (Security page).",
             "Below, every controller runs the same two test weeks with a fault injected."], art="safety")
with how_it_works("The six rules in order"):
    diagram("""
    flowchart LR
    P["MPC proposal"]:::ai --> R1{"R1 · sensor<br/>missing?"}:::guard
    R1 -- yes --> FB["Fallback setpoint"]:::ok
    R1 -- no --> R2{"R2 · conditions never<br/>seen in training?"}:::guard
    R2 -- yes --> FB
    R2 -- no --> R6{"R6 · data forged<br/>or replayed?"}:::guard
    R6 -- yes --> NW["No warmer than now<br/>(or than fallback)"]:::ok
    R6 -- no --> R5{"R5 · hardware fault<br/>reported? (agent cases)"}:::guard
    R5 -- no --> R3{"R3 · rack already<br/>near 27 °C?"}:::guard
    R5 -- yes --> NW
    NW --> R3
    R3 -- yes --> CO["Cool 2 °C now"]:::ok
    R3 -- no --> R4["R4 · max ±1 °C per step,<br/>stay within 16–24 °C"]:::guard
    R4 --> SEND["Send command"]:::ok
    """, alt="Safety filter: R1 missing sensor and R2 unfamiliar conditions go to fallback, R6 untrusted data and R5 hardware fault block warmer setpoints, R3 near limit cools 2 degrees, R4 limits rate and range")
    st.caption("The MPC only *proposes*. Six rules check every command before it is sent. "
                f"Fallback = the proven fixed setpoint of **{B['fixed_sp']:.0f} °C**, so losing the AI returns the room to how "
                "it was run before. Each fault scenario below runs all controllers through the same two test weeks. "
                "R5 takes the Hardware Engineer's constraint, so it fires in agent cases; the closed-loop study below has "
                "no hardware faults and shows 0 for it. R6 fires only under attack: 0 here, and the Security page shows the "
                "attack runs.")
fired = {}
for key in SC:
    rules = LOGS[key, "ai"]["rules"].fillna("").str.split(",").explode()
    fired[key] = rules[rules != ""].value_counts()
cols = st.columns(3) + st.columns(3)
for col, (rule, text) in zip(cols, RULES.items()):
    with col.container(border=True, height="stretch"):
        st.markdown(f"**{rule.split('_')[0]}** · {text}")
        st.caption(" · ".join(f"{SC[s].title}: {int(fired[s].get(rule, 0))}" for s in SC))
pick = st.segmented_control("Scenario", ["sensor_failure", "plant_change", "load_surge", "normal"], default="sensor_failure",
                            format_func=lambda s: SC[s].title) or "sensor_failure"
scen = SC[pick]
st.caption(f"**{scen.title}.** {scen.story}")
keys = ["fixed", "rule", "ai"] + (["ai_unsafe"] if (pick, "ai_unsafe") in LOGS else [])
table = B["summary"].set_index(["scenario", "key"]).loc[pick].loc[keys]
show_cols = {"controller": "Controller", "violation_minutes": "Minutes > 27 °C", "hottest_inlet_c": "Hottest inlet (°C)",
             "degree_hours_over": "°C·h over limit", "fallback_steps": "Fallback steps", "emergency_steps": "Emergency steps",
             "cooling_kwh": "Cooling kWh"}
st.dataframe(table[list(show_cols)].rename(columns=show_cols).style.format(
    {"Hottest inlet (°C)": "{:.2f}", "°C·h over limit": "{:.2f}", "Cooling kWh": "{:,.0f}"}), hide_index=True, width="stretch")
if scen.highlight:
    center, hours = pd.Timestamp(scen.highlight[0][0]), scen.highlight[0][1]
else:
    worst = LOGS[pick, "ai"]["max_inlet_c"].idxmax()
    center, hours = worst - pd.Timedelta(hours=2), 2
lo, hi = center - pd.Timedelta(hours=5), center + pd.Timedelta(hours=hours + 5)
fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.09,
                    subplot_titles=("True hottest inlet (°C)", "Setpoint sent (°C)"))
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
show(style(fig, height=480, title=f"Zoom on the first event · {center:%a %d %b}"))
takeaways = {
    "sensor_failure": "The rule-based controller trusts the remaining (cooler) sensors and lets B5/B6 overheat. The AI "
                      "without a safety filter does the same. With the filter, missing data → fallback setpoint → no overheating.",
    "plant_change": "The room no longer matches the training data. The fixed setpoint that used to be safe now overheats for "
                    "hours. The AI notices its forecasts are too low and corrects itself, but a few short exceedances remain at "
                    "the batch start — a cue to retrain on new data.",
    "load_surge": "Nobody can forecast a job that has never happened before. The AI runs closer to the limit, so it "
                  "is hit harder in the first 15 minutes; the 'too hot now' rule cools by 2 °C immediately.",
    "normal": "In normal operation no rule except the rate limit and an occasional 'too hot now' needs to step in.",
}
st.info(takeaways[pick])
