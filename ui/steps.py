"""The five steps of the 15-minute loop, one function each (How it works page). Only the selected step runs.

Each step shows one sentence, its key numbers and one main picture; everything else is in "More detail".
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from predictive_cooling import config as C
from predictive_cooling import forecast
from predictive_cooling.mpc import MPC
from predictive_cooling.safety import RULES
from ui.common import (AXIS, B, CLEAN, CTRL, INK, INK2, LIMIT, LOGS, MODEL, MUTED, QTY, RAW, SC, SURFACE, diagram, how_it_works,
                       kpi, kpi_row, limit_line, moment, show, style)


def floor_map(values: dict, title):
    """values: rack -> inlet °C (may be NaN). Rows A (top) and B (bottom) share the cold aisle."""
    z = [[values.get(r, np.nan) for r in C.ROWS["A"]], [np.nan] * 6, [values.get(r, np.nan) for r in C.ROWS["B"]]]
    scale = [[0.0, "#184f95"], [0.25, "#6da7ec"], [0.5, "#f0efec"], [0.75, "#ec8a89"], [1.0, "#a82e2e"]]
    fig = go.Figure(go.Heatmap(z=z, x=list(range(6)), y=["Row A", "Cold aisle", "Row B"],
                               zmin=18, zmax=28, colorscale=scale, xgap=4, ygap=4, hoverinfo="skip",
                               colorbar=dict(title=dict(text="Inlet °C"), thickness=10, len=0.9)))
    for row_i, row in [(0, "A"), (2, "B")]:
        for col_i, rack in enumerate(C.ROWS[row]):
            v = values.get(rack, np.nan)
            text = f"<b>{rack}</b><br>{'—' if np.isnan(v) else f'{v:.1f} °C'}<br><span style='font-size:10px'>{C.RACK_ROLE[rack]}</span>"
            light = np.isnan(v) or 20.5 <= v <= 25.5
            fig.add_annotation(x=col_i, y=row_i, text=text, showarrow=False, font=dict(color=INK if light else "white", size=12))
    fig.add_annotation(x=2.5, y=1, text="cold aisle  ←  cold air from the CRAH units on the left wall", showarrow=False,
                       font=dict(color=INK2, size=12))
    fig.update_yaxes(autorange="reversed", showgrid=False, showline=False)
    fig.update_xaxes(showgrid=False, showline=False, showticklabels=False)
    return style(fig, height=300, title=title, legend=False, hover=False)


# ---- 1 · sensors ----------------------------------------------------------------------------
def sensors():
    st.markdown("Every 15 minutes the room reports **12 rack inlet temperatures**, power meters, the cooling units and the "
                "weather. Each inlet must stay at or below **27 °C**; rack **B6** (GPU, far end) is always the hottest.")
    ts = moment()
    reading = CLEAN.loc[ts] if ts in CLEAN.index else None
    if reading is None or pd.isna(reading["max_inlet_c"]):
        st.warning("No complete reading at this time (logger gap). Try another time.", icon=":material/signal_disconnected:")
    else:
        kpi_row(kpi("Hottest inlet", f"{reading['max_inlet_c']:.1f} °C", f"rack {reading['hottest_rack']}"),
                kpi("Setpoint", f"{reading['crah_setpoint_c']:.0f} °C", help="Supply-air setpoint: the one knob the AI controls"),
                kpi("IT power", f"{reading['it_power_kw']:.0f} kW"), kpi("Cooling power", f"{reading['cooling_kw']:.0f} kW"),
                kpi("PUE", f"{reading['pue']:.2f}", help="Facility power ÷ IT power. 1.0 would be perfect."))
        show(floor_map({r: reading[f"inlet_{r}_c"] for r in C.RACKS}, f"Rack inlet temperatures · {ts:%a %d %b %H:%M}"))
    with how_it_works("More detail: the whole day, any day, and the raw file", icon=":material/table_chart:"):
        day = st.date_input("Day", value=ts.date(), min_value=CLEAN.index.min().date(), max_value=CLEAN.index.max().date(),
                            key="steps_day")
        frame = CLEAN.loc[str(day)]
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07, row_heights=[0.42, 0.33, 0.25],
                            subplot_titles=("Temperature (°C)", "Power (kW)", "Outdoor (°C)"))
        fig.add_scatter(x=frame.index, y=frame["max_inlet_c"], name="Hottest rack inlet", line=dict(color=QTY["temp"], width=2),
                        row=1, col=1)
        fig.add_scatter(x=frame.index, y=frame["crah_setpoint_c"], name="Supply-air setpoint",
                        line=dict(color=INK2, width=2, shape="hv"), row=1, col=1)
        limit_line(fig, 1, 1)
        fig.add_scatter(x=frame.index, y=frame["it_power_kw"], name="IT power", line=dict(color=QTY["it"], width=2), row=2, col=1)
        fig.add_scatter(x=frame.index, y=frame["cooling_kw"], name="Cooling power", line=dict(color=QTY["cooling"], width=2),
                        row=2, col=1)
        fig.add_scatter(x=frame.index, y=frame["outdoor_temp_c"], name="Outdoor air", line=dict(color=MUTED, width=2), row=3, col=1)
        show(style(fig, height=480, title=f"The whole day · {pd.Timestamp(day):%A %d %B}"))
        st.caption("The 01:00–05:00 jump on weekdays is the nightly GPU training batch; the afternoon bump is office load plus a "
                   "reporting job. Data: 13 weeks, 2 Feb – 3 May 2026, one reading every 15 minutes (8,718 rows × 25 columns).")
        st.download_button("Download sensor_history.csv", C.DATA_PATH.read_bytes, "sensor_history.csv", "text/csv",
                           icon=":material/download:")
        st.dataframe(RAW.head(200), width="stretch", height=240)


# ---- 2 · clean ------------------------------------------------------------------------------
def cleaning():
    st.markdown("Real logs are messy: sensors drop out, send impossible values (85 °C) or get stuck. **Four rules** clean the "
                "data, then it is split **by time**, so the model is scored on weeks it never saw.")
    q = B["quality"]
    kpi_row(kpi("Logger gaps", f"{q.attrs.get('gap_rows', 0)} rows", help="Missing timestamps put back on the 15-min grid"),
            kpi("Impossible values", f"{int(q['impossible'].sum())}", help="e.g. 85 °C or −40 °C from a bad packet"),
            kpi("Stuck readings", f"{int(q['stuck'].sum())}", help="Same exact value 6+ times in a row"),
            kpi("Holes filled", f"{int(q['filled'].sum())}", help="Interpolated when the hole is ≤ 1 hour"))
    issues = q[(q[["impossible", "stuck", "missing"]].sum(axis=1)) > 0].sort_values("stuck", ascending=False)
    sensor = st.selectbox("Sensor", list(issues.index), index=0, key="steps_sensor")
    bad = RAW[sensor].isna() | (RAW[sensor] != CLEAN[sensor].reindex(RAW.index))
    worst_day = bad.groupby(RAW.index.date).sum().idxmax()
    raw_day, clean_day = RAW.loc[str(worst_day), sensor], CLEAN.loc[str(worst_day), sensor]
    fig = go.Figure()
    fig.add_scatter(x=raw_day.index, y=raw_day, name="Raw log", mode="lines+markers", line=dict(color=MUTED, width=1.5),
                    marker=dict(size=4))
    fig.add_scatter(x=clean_day.index, y=clean_day, name="Cleaned", line=dict(color=QTY["temp"], width=2))
    removed = raw_day[bad.loc[str(worst_day)] & raw_day.notna()]
    fig.add_scatter(x=removed.index, y=removed, name="Removed", mode="markers", marker=dict(color=LIMIT, size=9, symbol="x"))
    low, high = clean_day.min(), clean_day.max()
    fig.update_yaxes(range=[low - 2, high + 2] if pd.notna(low) else None)
    show(style(fig, height=320, title=f"{sensor} on {pd.Timestamp(worst_day):%a %d %b}, its worst day"))
    with how_it_works("More detail: the rules, every sensor's problems and the time split", icon=":material/rule:"):
        diagram("""
flowchart LR
    R["Raw log"]:::step --> A["1 · back on the<br/>15-min grid"]:::step --> B["2 · impossible<br/>values → missing"]:::guard
    B --> S["3 · stuck sensor<br/>(6+ repeats) → missing"]:::guard --> F["4 · fill holes<br/>≤ 1 hour"]:::step
    F --> T["Train<br/>weeks 1–9"]:::ai
    F --> V["Validate<br/>weeks 10–11"]:::step
    F --> X["Test<br/>weeks 12–13"]:::ok
""", alt="Cleaning rules: grid, impossible values, stuck sensors, fill short holes, then a time-based train, validation and test split")
        st.caption("Holes longer than 1 hour stay missing and those rows are not used for training. Train weeks 1–9 (to 6 Apr), "
                   "validation weeks 10–11 (tune baselines and safety margins), test weeks 12–13 (20 Apr – 3 May).")
        st.dataframe(issues.astype(int), width="stretch", height=260)


# ---- 3 · forecast ---------------------------------------------------------------------------
def forecasting():
    acc = B["accuracy"]
    mae = acc.set_index(["kind", "horizon_min"])["inlet_mae_c"]
    nrmse = acc.set_index(["kind", "horizon_min"])["cooling_nrmse_pct"]
    st.markdown("The model answers: *if we use this setpoint plan, how hot will the hottest rack be, and how much power will we "
                "use, 15–60 minutes from now?* It learned the **01:00 GPU batch** from history, so it sees the heat coming.")
    kpi_row(kpi("Error, 15 min ahead", f"{mae['gbm', 15]:.2f} °C", "target ≤ 1 °C"),
            kpi("Error, 60 min ahead", f"{mae['gbm', 60]:.2f} °C", f"persistence {mae['persistence', 60]:.2f} °C"),
            kpi("Cooling power error", f"{nrmse['gbm', 60]:.1f} %", "60 min · target ≤ 10 %"))
    day = moment().date()
    part = B["samples"][4].loc[str(day)]
    fig = go.Figure()
    fig.add_scatter(x=part.index, y=part["actual_max_inlet_c"], name="Actual", line=dict(color=INK, width=2))
    fig.add_scatter(x=part.index, y=part["persistence_max_inlet_c"], name="Persistence (copy the present)",
                    line=dict(color=MUTED, width=2, dash="dot"))
    fig.add_scatter(x=part.index, y=part["gbm_max_inlet_c"], name="Gradient boosting (ML)", line=dict(color=MODEL["gbm"], width=2))
    fig.update_yaxes(title="hottest inlet (°C)")
    show(style(fig, height=330, title=f"Forecast made 60 min earlier vs what happened · {pd.Timestamp(day):%a %d %b}"))
    with how_it_works("More detail: error by horizon and what the model looks at", icon=":material/insights:"):
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            for kind, label in forecast.Forecaster.KINDS.items():
                p = acc[acc["kind"] == kind]
                fig.add_scatter(x=p["horizon_min"], y=p["inlet_mae_c"], name=label, mode="lines+markers",
                                line=dict(color=MODEL[kind], width=2, dash="dot" if kind == "persistence" else None),
                                marker=dict(size=9, line=dict(color=SURFACE, width=2)))
            fig.update_xaxes(title="minutes ahead", tickvals=[15, 30, 45, 60])
            fig.update_yaxes(title="mean absolute error (°C)", rangemode="tozero")
            show(style(fig, height=320, title="Hottest-inlet error by horizon (test weeks)"))
        with c2:
            imp = B["importance"][C.HORIZON].head(8).iloc[::-1]
            fig = go.Figure(go.Bar(x=imp["importance"], y=imp["feature"], orientation="h", marker_color=MODEL["gbm"], width=0.55,
                                   hovertemplate="%{y}: %{x:.3f} °C<extra></extra>"))
            fig.update_xaxes(title="error increase when shuffled (°C)")
            show(style(fig, height=320, title="What the 60-min model looks at", legend=False, hover="closest"))
        table = acc.pivot(index="model", columns="horizon_min", values="inlet_mae_c").reindex(list(forecast.Forecaster.KINDS.values()))
        table.columns = [f"{c} min" for c in table.columns]
        st.dataframe(table.style.format("{:.2f}"), width="stretch")
        st.caption("Gradient boosting with physics constraints (warmer setpoint → warmer racks, less chiller power), one model "
                   "per target × horizon. Inputs: the current sensors + the setpoint plan for the next 4 × 15 minutes.")
    with how_it_works("Try it: your own setpoint plan", icon=":material/tune:"):
        states = forecast.state_features(CLEAN.loc[C.VAL_END:]).dropna()
        when = states.index[states.index.get_indexer([moment()], method="nearest")[0]]
        state = states.loc[when]
        now_sp = float(state["setpoint_prev_c"])
        cols = st.columns(4)
        plan = [cols[i].number_input(f"+{15 * i} min", min_value=C.SP_MIN, max_value=C.SP_MAX, value=now_sp, step=1.0,
                                     format="%.0f", key=f"wi{i}") for i in range(4)]
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
        show(style(fig, height=290, title=f"{when:%a %d %b %H:%M} · predicted energy next hour: {energy:,.1f} kWh"))


# ---- 4 · plan (MPC) -------------------------------------------------------------------------
def planning():
    st.markdown("Like a GPS: try **all 81 setpoint plans** for the next hour (each 15 minutes −1, 0 or +1 °C), drop the ones "
                "forecast to overheat, take the cheapest. Only the **first step** is applied; 15 minutes later it plans again.")
    ai_log = LOGS["normal", "ai"]
    t = moment()
    row = ai_log.loc[t]
    state = pd.Series({c: row[f"x_{c}"] for c in forecast.STATE_FEATURES})
    plans = MPC(B["forecaster"], B["margins"]).evaluate_plans(state, row["setpoint_in_use"], row["bias_c"])
    safe = plans[plans["safe"]]
    best = safe["cost"].idxmin() if len(safe) else plans[plans["within_limits"]]["peak_guarded_c"].idxmin()
    chosen = plans.loc[best]
    kpi_row(kpi("Setpoint in use", f"{row['setpoint_in_use']:.0f} °C"), kpi("Safe plans", f"{len(safe)} of 81"),
            kpi("Apply now", f"{chosen['first_sp']:.0f} °C", "first step"),
            kpi("Chosen plan", chosen["plan"].replace(" ", "→"), "°C, next hour"))
    if row["command"] != chosen["first_sp"]:
        st.info(f"The safety filter changed it to {row['command']:.0f} °C ({row['rules']}).", icon=":material/shield:")
    fig = go.Figure()
    for flag, name, color in [(False, "Too hot (rejected)", AXIS), (True, "Safe", MODEL["gbm"])]:
        p = plans[(plans["safe"] == flag) & plans["within_limits"]]
        fig.add_scatter(x=p["peak_guarded_c"], y=p["energy_kwh"], mode="markers", name=name,
                        marker=dict(size=9, color=color, line=dict(color=SURFACE, width=2)), customdata=p[["plan"]].to_numpy(),
                        hovertemplate="plan %{customdata[0]} °C<br>peak %{x:.2f} °C (with margin)<br>%{y:.1f} kWh<extra></extra>")
    fig.add_scatter(x=[chosen["peak_guarded_c"]], y=[chosen["energy_kwh"]], mode="markers+text", name="Chosen",
                    marker=dict(size=18, color="rgba(0,0,0,0)", line=dict(color=INK, width=2.5)),
                    text=[f"  chosen: {chosen['plan']}"], textposition="middle right", textfont=dict(color=INK, size=12),
                    hoverinfo="skip")
    fig.add_vline(x=C.INLET_LIMIT, line=dict(color=LIMIT, width=1.5), annotation_text="27 °C limit",
                  annotation_font=dict(color=LIMIT, size=11))
    fig.update_xaxes(title="forecast peak of the hottest inlet next hour, incl. safety margin (°C)")
    fig.update_yaxes(title="forecast energy next hour (kWh)")
    show(style(fig, height=360, title=f"81 plans at {t:%a %d %b %H:%M}", hover="closest"))
    with how_it_works("More detail: every plan's forecast and the AI's whole day", icon=":material/route:"):
        fig = make_subplots(rows=1, cols=2, subplot_titles=("Forecast hottest inlet, every plan (°C)", "Chosen setpoints (°C)"))
        future = [t + pd.Timedelta(minutes=15 * (i + 1)) for i in range(C.HORIZON)]
        for i, p in plans[plans["within_limits"]].iterrows():
            if i != best:
                fig.add_scatter(x=[t] + future, y=[row["measured_max_inlet_c"]] + [p[f"inlet_{k}"] for k in range(1, 5)],
                                mode="lines", line=dict(color=AXIS, width=1), showlegend=False, hoverinfo="skip", row=1, col=1)
        fig.add_scatter(x=[t] + future, y=[row["measured_max_inlet_c"]] + [chosen[f"inlet_{k}"] for k in range(1, 5)],
                        name="Chosen plan", mode="lines+markers", line=dict(color=MODEL["gbm"], width=2.5), marker=dict(size=8),
                        row=1, col=1)
        limit_line(fig, 1, 1)
        sps = [chosen[f"sp_{k}"] for k in range(1, 5)]
        sps = sps + sps[-1:]                       # step k is held from t+15(k-1) to t+15k
        fig.add_scatter(x=[t] + future, y=sps, name="Chosen setpoints", line=dict(color=INK2, width=2, shape="hv"), row=1, col=2)
        fig.update_yaxes(range=[min(sps) - 2, max(sps) + 2], dtick=1, row=1, col=2)
        show(style(fig, height=300, legend=False))
        day_log = ai_log.loc[str(t.date())]
        fig = go.Figure()
        fig.add_scatter(x=day_log.index, y=day_log["max_inlet_c"], name="Hottest inlet (true)", line=dict(color=QTY["temp"], width=2))
        fig.add_scatter(x=day_log.index, y=day_log["command"], name="AI setpoint", line=dict(color=CTRL["ai"], width=2, shape="hv"))
        limit_line(fig)
        fig.add_vline(x=t, line=dict(color=INK2, width=1))
        show(style(fig, height=300, title="The AI's whole day: it pre-cools before 01:00 and runs warmer when racks are quiet"))
        st.caption(f"Safety margin = the 99th percentile of how much the model under-predicted on the validation weeks "
                   f"({', '.join(f'{m:.2f}' for m in B['margins'])} °C at +15…60 min). Feedback correction in use now: "
                   f"{row['bias_c']:+.2f} °C (the last forecast error, carried into the next forecast).")


# ---- 5 · safety -----------------------------------------------------------------------------
SAFETY_TABLE = [
    ("R1", "Missing data", "a rack inlet sensor is missing", "head to the proven fallback setpoint"),
    ("R2", "Unfamiliar", "conditions far outside the training data", "fallback setpoint"),
    ("R6", "Untrusted", "the data looks forged or replayed (Security)", "never warmer than now"),
    ("R5", "Hardware", "a cooling-equipment problem (Data center)", "never warmer than now"),
    ("R3", "Too hot now", "a rack is within 0.3 °C of 27 °C", "cool by 2 °C at once"),
    ("R4", "Limits", "always", "at most ±1 °C per 15 min, within 16–24 °C"),
]


def safety():
    st.markdown(f"The AI only **proposes**. Six rules check every command before it is sent; when in doubt the room goes back "
                f"to the old proven setpoint (**{B['fixed_sp']:.0f} °C**), so it is never worse than before.")
    st.dataframe(pd.DataFrame(SAFETY_TABLE, columns=["Rule", "Name", "When", "Then"]), hide_index=True, width="stretch")
    st.page_link("app_pages/results.py", label="See the rules at work in the fault scenarios (Results)", icon=":material/arrow_forward:")
    with how_it_works("More detail: the rules in order, and how often each fired", icon=":material/shield:"):
        diagram("""
flowchart LR
    P["MPC proposal"]:::ai --> R1{"R1 · sensor<br/>missing?"}:::guard
    R1 -- yes --> FB["Fallback setpoint"]:::ok
    R1 -- no --> R2{"R2 · never seen<br/>in training?"}:::guard
    R2 -- yes --> FB
    R2 -- no --> R6{"R6 · forged or<br/>replayed?"}:::guard
    R6 -- yes --> NW["No warmer than now<br/>(or than fallback)"]:::ok
    R6 -- no --> R5{"R5 · hardware<br/>fault?"}:::guard
    R5 -- no --> R3{"R3 · rack near<br/>27 °C?"}:::guard
    R5 -- yes --> NW
    NW --> R3
    R3 -- yes --> CO["Cool 2 °C now"]:::ok
    R3 -- no --> R4["R4 · ±1 °C per step,<br/>16–24 °C"]:::guard
    R4 --> SEND["Send command"]:::ok
""", alt="Safety filter: R1 and R2 go to fallback, R6 and R5 block warmer setpoints, R3 cools 2 degrees, R4 limits rate and range")
        fired = {}
        for key in SC:
            rules = LOGS[key, "ai"]["rules"].fillna("").str.split(",").explode()
            fired[key] = rules[rules != ""].value_counts()
        counts = pd.DataFrame({SC[s].title: [int(fired[s].get(r, 0)) for r in RULES] for s in SC},
                              index=[f"{r.split('_')[0]} · {text}" for r, text in RULES.items()])
        st.dataframe(counts, width="stretch")
        st.caption("Times each rule changed the AI's command over the two test weeks, per scenario. R5 and R6 act in agent "
                   "cases and attacks (Data center and Security pages).")


STEPS = {"1 · Sensors": sensors, "2 · Clean": cleaning, "3 · Forecast": forecasting, "4 · Plan": planning, "5 · Safety": safety}
