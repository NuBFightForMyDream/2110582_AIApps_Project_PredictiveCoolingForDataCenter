"""4 · Plan (MPC): 81 setpoint plans, keep the safe ones, pick the cheapest."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from predictive_cooling import config as C, forecast
from predictive_cooling.mpc import MPC
from ui.common import (AXIS, B, CTRL, INK, INK2, LIMIT, LOGS, MODEL, QTY, SURFACE, diagram, how_it_works, limit_line, moment,
                       note_metric, page_header, show, style)


page_header("Plan (MPC)", ":material/route:", "How the controller chooses a setpoint, at the moment picked in the sidebar.",
            ["Think of it like GPS: try every route for the next hour, drop the ones that overheat, take the cheapest.",
             "Only the **first step** is applied. 15 minutes later it plans again with fresh data."], art="mpc")
with how_it_works("81 plans, step by step"):
    diagram("""
    flowchart LR
    N["Setpoint now"]:::step --> C["Each 15 min:<br/>−1, 0 or +1 °C"]:::step
    C --> P["4 steps → 3⁴ =<br/>81 plans"]:::step
    P --> F["Forecast every plan"]:::ai
    F --> D{"peak + safety margin<br/>≤ 27 °C?"}:::guard
    D -- no --> X["Rejected"]:::guard
    D -- yes --> E["Cheapest safe plan<br/>(least kWh)"]:::ok
    E --> A["Apply only<br/>its first step"]:::ok
    """, alt="MPC: 3 choices per step over 4 steps make 81 plans; forecast each, reject unsafe, choose cheapest, apply first step")
    st.caption("Each 15-minute step can go **−1, 0 or +1 °C**; four steps make **3⁴ = 81 plans**. "
                "The forecaster scores each plan, plans whose predicted hottest inlet + safety margin crosses 27 °C are "
                "thrown out, and the cheapest remaining plan wins. Only its first step is applied; 15 minutes later the "
                "controller looks again with fresh sensor data (and corrects itself for its last forecast error).")
ai_log = LOGS["normal", "ai"]
c1, c2 = st.columns([1, 2])
t = moment()
d = t.date()
row = ai_log.loc[t]
state = pd.Series({c: row[f"x_{c}"] for c in forecast.STATE_FEATURES})
mpc = MPC(B["forecaster"], B["margins"])
plans = mpc.evaluate_plans(state, row["setpoint_in_use"], row["bias_c"])
safe = plans[plans["safe"]]
best = safe["cost"].idxmin() if len(safe) else plans[plans["within_limits"]]["peak_guarded_c"].idxmin()
chosen = plans.loc[best]
with c1:
    a, b = st.columns(2)
    a.metric("Setpoint in use", f"{row['setpoint_in_use']:.0f} °C", border=True)
    b.metric("Hottest inlet now", f"{row['measured_max_inlet_c']:.1f} °C", border=True)
    a, b = st.columns(2)
    a.metric("Safe plans", f"{len(safe)} of 81", border=True)
    note_metric(b, "Apply now", f"{chosen['first_sp']:.0f} °C", "first step of the plan", border=True)
    st.markdown(f"**Chosen plan** · {chosen['plan'].replace(' ', ' → ')} °C")
    sent = row["command"]
    if sent != chosen["first_sp"]:
        st.info(f"The safety filter changed it to {sent:.0f} °C ({row['rules']}).")
    st.caption(f"Feedback correction in use: {row['bias_c']:+.2f} °C · margins "
               + ", ".join(f"{m:.2f}" for m in B["margins"]) + " °C at +15…60 min")
with c2:
    fig = go.Figure()
    for flag, name, color in [(False, "Too hot (rejected)", AXIS), (True, "Safe", MODEL["gbm"])]:
        part = plans[(plans["safe"] == flag) & plans["within_limits"]]
        fig.add_scatter(x=part["peak_guarded_c"], y=part["energy_kwh"], mode="markers", name=name,
                        marker=dict(size=9, color=color, line=dict(color=SURFACE, width=2)),
                        customdata=part[["plan"]].to_numpy(),
                        hovertemplate="plan %{customdata[0]} °C<br>peak %{x:.2f} °C (with margin)<br>%{y:.1f} kWh<extra></extra>")
    fig.add_scatter(x=[chosen["peak_guarded_c"]], y=[chosen["energy_kwh"]], mode="markers+text", name="Chosen",
                    marker=dict(size=18, color="rgba(0,0,0,0)", line=dict(color=INK, width=2.5)),
                    text=[f"  chosen: {chosen['plan']}"], textposition="middle right", textfont=dict(color=INK, size=12),
                    hoverinfo="skip")
    fig.add_vline(x=C.INLET_LIMIT, line=dict(color=LIMIT, width=1.5), annotation_text="27 °C limit",
                  annotation_font=dict(color=LIMIT, size=11))
    fig.update_xaxes(title="predicted peak hottest inlet in the next hour, incl. safety margin (°C)")
    fig.update_yaxes(title="predicted energy next hour (kWh)")
    show(style(fig, height=360, title=f"81 plans at {t:%a %d %b %H:%M}", hover="closest"))

fig = make_subplots(rows=1, cols=2, subplot_titles=("Predicted hottest inlet for every plan (°C)", "Setpoint of the chosen plan (°C)"))
future = [t + pd.Timedelta(minutes=15 * (i + 1)) for i in range(C.HORIZON)]
for i, p in plans[plans["within_limits"]].iterrows():
    if i == best:
        continue
    fig.add_scatter(x=[t] + future, y=[row["measured_max_inlet_c"]] + [p[f"inlet_{k}"] for k in range(1, 5)], mode="lines",
                    line=dict(color=AXIS, width=1), showlegend=False, hoverinfo="skip", row=1, col=1)
fig.add_scatter(x=[t] + future, y=[row["measured_max_inlet_c"]] + [chosen[f"inlet_{k}"] for k in range(1, 5)], name="Chosen plan",
                mode="lines+markers", line=dict(color=MODEL["gbm"], width=2.5), marker=dict(size=8), row=1, col=1)
limit_line(fig, 1, 1)
sps = [chosen[f"sp_{k}"] for k in range(1, 5)]
sps = sps + sps[-1:]                       # step k is held from t+15(k-1) to t+15k
fig.add_scatter(x=[t] + future, y=sps, name="Chosen setpoints", line=dict(color=INK2, width=2, shape="hv"), row=1, col=2)
fig.update_yaxes(range=[min(sps) - 2, max(sps) + 2], dtick=1, row=1, col=2)
show(style(fig, height=300, legend=False))

day_log = ai_log.loc[str(d)]
fig = go.Figure()
fig.add_scatter(x=day_log.index, y=day_log["max_inlet_c"], name="Hottest inlet (true)", line=dict(color=QTY["temp"], width=2))
fig.add_scatter(x=day_log.index, y=day_log["command"], name="AI setpoint", line=dict(color=CTRL["ai"], width=2, shape="hv"))
fig.add_scatter(x=day_log.index, y=day_log["it_load_pct"] / 10 + 10, name="IT load (scaled: 10 + load/10)",
                line=dict(color=AXIS, width=1.5), visible="legendonly")
limit_line(fig)
fig.add_vline(x=t, line=dict(color=INK2, width=1))
show(style(fig, height=300, title="The AI's whole day: it pre-cools before 01:00 and runs warmer when racks are quiet"))
