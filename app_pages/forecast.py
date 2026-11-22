"""3 · Forecast: can the model see the next hour?"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from predictive_cooling import config as C, forecast
from ui.common import AXIS, B, CLEAN, INK, INK2, MODEL, MUTED, SURFACE, diagram, how_it_works, limit_line, moment, page_header, show, style


_acc = B["accuracy"]
gbm_mae_60 = _acc[(_acc["kind"] == "gbm") & (_acc["horizon_min"] == 60)]["inlet_mae_c"].iloc[0]
page_header("Forecast", ":material/insights:", "Can the model see the next hour?",
            ["The model answers: *if we use this setpoint plan, how hot will the hottest rack be, and how much power will we "
             "use, 15–60 minutes from now?*",
             f"**Gradient boosting** errs by about **{gbm_mae_60:.2f} °C** one hour ahead; just copying the current value "
             "(persistence) is several times worse.",
             "Its edge: it learned the **01:00 GPU batch** from history, so it sees the heat coming before it arrives."],
            art="forecast")
with how_it_works("What goes in and what comes out"):
    diagram("""
    flowchart LR
    I["Now: sensors, time of day,<br/>weekday/weekend"]:::step --> M["Forecaster (ML)<br/>12 small models"]:::ai
    P["A setpoint plan<br/>for the next 4 × 15 min"]:::step --> M
    M --> O1["Hottest rack inlet"]:::ok
    M --> O2["Cooling power"]:::ok
    M --> O3["IT power"]:::ok
    """, alt="Forecaster inputs (current sensors and a setpoint plan) and outputs (hottest inlet, cooling power, IT power)")
    st.caption("Inputs: current sensors (hottest/average inlet, supply air, IT and cooling power, outdoor "
                "temperature, time of day, weekend) **+ the setpoint plan for the next 4 × 15 min**. Outputs at +15/30/45/60 min: "
                "hottest inlet, cooling power, IT power. Scored on the 2 test weeks the model never saw.")
acc = B["accuracy"]
c1, c2 = st.columns(2)
with c1:
    fig = go.Figure()
    for kind, label in forecast.Forecaster.KINDS.items():
        part = acc[acc["kind"] == kind]
        fig.add_scatter(x=part["horizon_min"], y=part["inlet_mae_c"], name=label, mode="lines+markers",
                        line=dict(color=MODEL[kind], width=2, dash="dot" if kind == "persistence" else None),
                        marker=dict(size=9, line=dict(color=SURFACE, width=2)))
        last = part.iloc[-1]
        fig.add_annotation(x=last["horizon_min"], y=last["inlet_mae_c"], text=f"{last['inlet_mae_c']:.2f}", xshift=22,
                           showarrow=False, font=dict(color=INK2, size=11))
    fig.add_hline(y=1.0, line=dict(color=AXIS, width=1), annotation_text="proposal target ≤ 1 °C at 15 min",
                  annotation_position="top left", annotation_font=dict(size=11, color=INK2))
    fig.update_xaxes(title="forecast horizon (minutes ahead)", tickvals=[15, 30, 45, 60])
    fig.update_yaxes(title="mean absolute error (°C)", rangemode="tozero")
    show(style(fig, height=340, title="Hottest-inlet error grows with horizon — less for ML"))
with c2:
    table = acc.pivot(index="model", columns="horizon_min", values="inlet_mae_c").reindex(list(forecast.Forecaster.KINDS.values()))
    table.columns = [f"{c} min" for c in table.columns]
    st.markdown("**Hottest inlet, MAE (°C)** — target ≤ 1 °C at 15 min")
    st.dataframe(table.style.format("{:.2f}"), width="stretch")
    power = acc[acc["horizon_min"].isin([15, 60])].pivot(index="model", columns="horizon_min",
                                                           values=["cooling_nrmse_pct", "it_nrmse_pct"])
    power = power.reindex(list(forecast.Forecaster.KINDS.values()))
    power.columns = [f"{'Cooling' if a.startswith('cooling') else 'IT'} {h} min" for a, h in power.columns]
    st.markdown("**Power, NRMSE (% of mean)** — target ≤ 10 %")
    st.dataframe(power.style.format("{:.1f}"), width="stretch")

horizon = st.segmented_control("Forecast made this far ahead", [15, 30, 45, 60], default=60, format_func=lambda m: f"{m} min")
h = (horizon or 60) // 15
sample = B["samples"][h]
test_day = moment().date()                     # the day picked in the sidebar
part = sample.loc[str(test_day)]
fig = go.Figure()
fig.add_scatter(x=part.index, y=part["actual_max_inlet_c"], name="Actual", line=dict(color=INK, width=2))
fig.add_scatter(x=part.index, y=part["persistence_max_inlet_c"], name="Persistence", line=dict(color=MUTED, width=2, dash="dot"))
fig.add_scatter(x=part.index, y=part["gbm_max_inlet_c"], name="Gradient boosting (ML)", line=dict(color=MODEL["gbm"], width=2))
fig.update_yaxes(title="hottest inlet (°C)")
show(style(fig, height=330, title=f"Forecast made {h * 15} min earlier vs what happened · {pd.Timestamp(test_day):%a %d %b}"))
st.caption("Persistence is always late: it only notices the 01:00 GPU batch after it has started. "
           "The ML model learned from history that the batch starts at 01:00 on weekdays.")

c1, c2 = st.columns([1, 1.1])
with c1:
    imp = B["importance"][1 if h == 1 else C.HORIZON].head(8).iloc[::-1]
    fig = go.Figure(go.Bar(x=imp["importance"], y=imp["feature"], orientation="h", marker_color=MODEL["gbm"], width=0.55,
                           hovertemplate="%{y}: %{x:.3f} °C<extra></extra>"))
    fig.update_xaxes(title="error increase when shuffled (°C)")
    show(style(fig, height=330, title=f"What the {'15' if h == 1 else '60'}-min model looks at", legend=False, hover="closest"))
with c2:
    st.markdown("**Try it: what if we used this plan?**")
    test_frame = CLEAN.loc[C.VAL_END:]
    states = forecast.state_features(test_frame).dropna()
    when = st.select_slider("Moment (test weeks)", options=list(states.index), value=states.index[states.index.get_indexer([moment()], method='nearest')[0]],
                            format_func=lambda t: f"{t:%a %d %b %H:%M}")
    state = states.loc[when]
    now_sp = float(state["setpoint_prev_c"])
    cols = st.columns(4)
    plan = [cols[i].number_input(f"+{15 * i} min", min_value=C.SP_MIN, max_value=C.SP_MAX, value=now_sp, step=1.0,
                                 format="%.0f", key=f"wi{i}")
            for i in range(4)]
    pred = B["forecaster"].predict_plans(state, np.array([plan]))
    times = [when + pd.Timedelta(minutes=15 * (i + 1)) for i in range(4)]
    fig = go.Figure()
    fig.add_scatter(x=[when] + times, y=[state["max_inlet_c"]] + list(pred["max_inlet_c"][0]), name="Predicted hottest inlet",
                    mode="lines+markers", line=dict(color=MODEL["gbm"], width=2), marker=dict(size=8))
    fig.add_scatter(x=[when] + times, y=[state["max_inlet_c"]] + list(pred["max_inlet_c"][0] + np.array(B["margins"])),
                    name="+ safety margin", mode="lines", line=dict(color=MODEL["gbm"], width=1, dash="dot"))
    fig.add_scatter(x=[when] + times, y=plan + plan[-1:], name="Setpoint plan", line=dict(color=INK2, width=2, shape="hv"))
    limit_line(fig)
    energy = float((pred["cooling_kw"][0] + pred["it_power_kw"][0]).sum() * C.DT_H)
    show(style(fig, height=290, title=f"Predicted energy next hour: {energy:,.1f} kWh"))
