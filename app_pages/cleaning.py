"""2 · Clean data: the four cleaning rules and the time-based split."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from predictive_cooling import config as C
from ui.common import B, CLEAN, LIMIT, MUTED, QTY, RAW, diagram, how_it_works, kpi, kpi_row, page_header, show, style


page_header("Clean data", ":material/cleaning_services:", "Real logs are messy: fix them before anything learns from them.",
            ["Sensors drop out, send impossible values (85 °C) or get stuck. Training on that teaches the model nonsense.",
             "Four rules clean the data; then it is split **by time** so the model is tested on weeks it never saw."],
            art="cleaning")
q = B["quality"]
kpi_row(kpi("Readings on the grid", f"{len(CLEAN):,}"),
        kpi("Logger gaps", f"{q.attrs.get('gap_rows', 0)} rows", help="Missing timestamps put back on the 15-min grid"),
        kpi("Impossible values", f"{int(q['impossible'].sum())}", help="e.g. 85 °C or −40 °C from a bad packet"),
        kpi("Stuck-sensor readings", f"{int(q['stuck'].sum())}", help="Same exact value 6+ times in a row"),
        kpi("Short holes filled", f"{int(q['filled'].sum())}", help="Interpolated when the hole is ≤ 1 hour"))
with how_it_works("The four cleaning rules and the split"):
    diagram("""
    flowchart LR
    R["Raw log"]:::step --> A["1 · back on the<br/>15-min grid"]:::step --> B["2 · impossible<br/>values → missing"]:::guard
    B --> S["3 · stuck sensor<br/>(6+ repeats) → missing"]:::guard --> F["4 · fill holes<br/>≤ 1 hour"]:::step
    F --> T["Train<br/>weeks 1–9"]:::ai
    F --> V["Validate<br/>weeks 10–11"]:::step
    F --> X["Test<br/>weeks 12–13"]:::ok
    """, alt="Cleaning rules: grid, impossible values, stuck sensors, fill short holes, then a time-based train, validation and test split")
    st.caption("Rules: **1** put readings back on the 15-minute grid · **2** values outside the "
                "physical range become missing · **3** a sensor repeating the exact same value 6+ times is stuck → missing · "
                "**4** holes up to 1 hour are interpolated, longer ones stay missing and those rows are not used for training.")
issues = q[(q[["impossible", "stuck", "missing"]].sum(axis=1)) > 0].sort_values("stuck", ascending=False)
sensor = st.selectbox("Inspect a sensor", list(issues.index), index=0)
bad = RAW[sensor].isna() | (RAW[sensor] != CLEAN[sensor].reindex(RAW.index))
worst_day = (bad.groupby(RAW.index.date).sum().idxmax())
raw_day, clean_day = RAW.loc[str(worst_day), sensor], CLEAN.loc[str(worst_day), sensor]
fig = go.Figure()
fig.add_scatter(x=raw_day.index, y=raw_day, name="Raw log", mode="lines+markers", line=dict(color=MUTED, width=1.5), marker=dict(size=4))
fig.add_scatter(x=clean_day.index, y=clean_day, name="Cleaned", line=dict(color=QTY["temp"], width=2))
removed = raw_day[bad.loc[str(worst_day)] & raw_day.notna()]
fig.add_scatter(x=removed.index, y=removed, name="Removed", mode="markers", marker=dict(color=LIMIT, size=9, symbol="x"))
low, high = clean_day.min(), clean_day.max()
fig.update_yaxes(range=[low - 2, high + 2] if pd.notna(low) else None)
show(style(fig, height=320, title=f"{sensor} on {pd.Timestamp(worst_day):%a %d %b} (the day with most problems)"))
st.caption("Glitch values far outside the axis are removed too; the axis is zoomed to the real signal.")
c1, c2 = st.columns([1.3, 1])
with c1:
    st.dataframe(issues.astype(int), width="stretch", height=280)
with c2:
    split = pd.DataFrame([("Train the forecaster", C.START, C.TRAIN_END, "weeks 1-9"),
                          ("Validation: tune baselines + safety margins", C.TRAIN_END, C.VAL_END, "weeks 10-11"),
                          ("Test: score everything", C.VAL_END, str(CLEAN.index.max().date() + pd.Timedelta(days=1)), "weeks 12-13")],
                         columns=["Part", "Start", "End", "Weeks"])
    fig2 = go.Figure()
    start = pd.Timestamp(C.START)
    for i, row in split.iterrows():
        s, e = pd.Timestamp(row["Start"]), pd.Timestamp(row["End"])
        fig2.add_bar(y=["Data"], x=[(e - s).days], base=[(s - start).days], orientation="h", width=0.45,
                     marker_color=[MUTED, "#86b6ef", "#2a78d6"][i], name=f"{row['Part']} ({row['Weeks']})",
                     hovertemplate=f"{row['Part']}<br>{s:%d %b} – {(e - pd.Timedelta(days=1)):%d %b}<extra></extra>")
    fig2.update_layout(barmode="overlay")
    fig2.update_xaxes(title="days since 2 Feb 2026")
    fig2.update_yaxes(showticklabels=False)
    style(fig2, height=280, title="Chronological split (never shuffle time series)", hover="closest")
    fig2.update_layout(legend=dict(orientation="v", y=-0.45, yanchor="top"), margin=dict(b=90, t=46))
    show(fig2)
