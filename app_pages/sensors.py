"""1 · Sensors: what the room reports every 15 minutes."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from predictive_cooling import config as C
from ui.common import AXIS, CLEAN, INK, INK2, MUTED, QTY, RAW, TIMES, limit_line, moment, note_metric, page_header, show, style


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
            fig.add_annotation(x=col_i, y=row_i, text=text, showarrow=False,
                               font=dict(color=INK if light else "white", size=12))
    fig.add_annotation(x=2.5, y=1, text="cold aisle  ←  cold air from the CRAH units on the left wall", showarrow=False,
                       font=dict(color=INK2, size=12))
    fig.update_yaxes(autorange="reversed", showgrid=False, showline=False)
    fig.update_xaxes(showgrid=False, showline=False, showticklabels=False)
    return style(fig, height=300, title=title, legend=False, hover=False)


page_header("Sensors", ":material/sensors:", "What the room reports every 15 minutes: 12 rack inlets, power meters, the "
            "cooling units and the weather.",
            ["12 racks in two rows face one **cold aisle**; cold air comes from the CRAH units on the left wall.",
             "Each rack's **inlet temperature** must stay at or below **27 °C**. Red on the map = close to the limit.",
             "Rack **B6** (far end, GPU) is always the hottest, so it decides how warm the whole room can run."], art="sensors")

ts = moment()
if st.toggle("Browse the whole 13-week history", key="sensors_browse",
             help="By default the page follows the moment in the sidebar (the two test weeks)"):
    c1, c2 = st.columns([1, 2.2])
    day = c1.date_input("Day", value=ts.date(), min_value=CLEAN.index.min().date(), max_value=CLEAN.index.max().date())
    ts = pd.Timestamp(f"{day} {c2.select_slider('Time', options=TIMES, value=f'{ts:%H:%M}', key='sensors_time')}")
day = ts.date()
reading = CLEAN.loc[ts] if ts in CLEAN.index else None
if reading is None or pd.isna(reading["max_inlet_c"]):
    st.warning("No complete reading at this time (logger gap). Try another time.", icon=":material/signal_disconnected:")
else:
    left, right = st.columns([1, 2.1], vertical_alignment="center")
    with left:
        a, b = st.columns(2)
        a.metric("IT power", f"{reading['it_power_kw']:.0f} kW", border=True)
        b.metric("Cooling power", f"{reading['cooling_kw']:.0f} kW", border=True)
        a, b = st.columns(2)
        a.metric("PUE", f"{reading['pue']:.2f}", help="Facility power ÷ IT power. 1.0 would be perfect.", border=True)
        b.metric("Outdoor", f"{reading['outdoor_temp_c']:.1f} °C", border=True)
        a, b = st.columns(2)
        a.metric("Setpoint", f"{reading['crah_setpoint_c']:.0f} °C", help="Supply-air setpoint: the one knob the AI controls",
                 border=True)
        note_metric(b, "Hottest inlet", f"{reading['max_inlet_c']:.1f} °C", f"rack {reading['hottest_rack']}", border=True)
    with right:
        show(floor_map({r: reading[f"inlet_{r}_c"] for r in C.RACKS}, f"Rack inlet temperatures · {ts:%a %d %b %H:%M}"))

day_frame = CLEAN.loc[str(day)]
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07, row_heights=[0.42, 0.33, 0.25],
                    subplot_titles=("Temperature (°C)", "Power (kW)", "Outdoor (°C)"))
fig.add_scatter(x=day_frame.index, y=day_frame["max_inlet_c"], name="Hottest rack inlet", line=dict(color=QTY["temp"], width=2), row=1, col=1)
fig.add_scatter(x=day_frame.index, y=day_frame["crah_setpoint_c"], name="Supply-air setpoint", line=dict(color=INK2, width=2, shape="hv"), row=1, col=1)
limit_line(fig, 1, 1)
fig.add_scatter(x=day_frame.index, y=day_frame["it_power_kw"], name="IT power", line=dict(color=QTY["it"], width=2), row=2, col=1)
fig.add_scatter(x=day_frame.index, y=day_frame["cooling_kw"], name="Cooling power", line=dict(color=QTY["cooling"], width=2), row=2, col=1)
fig.add_scatter(x=day_frame.index, y=day_frame["outdoor_temp_c"], name="Outdoor air", line=dict(color=MUTED, width=2), row=3, col=1)
fig.add_vline(x=ts, line=dict(color=AXIS, width=1))
show(style(fig, height=520, title=f"The whole day · {pd.Timestamp(day):%A %d %B}"))
st.caption("The 01:00–05:00 jump on weekdays is the nightly GPU training batch; the afternoon bump is office load "
           "plus a reporting job. The old operator rule (and occasional setpoint step tests) chose the setpoint.")

with st.expander("Sensor dictionary and the raw file", icon=":material/table_chart:"):
    dictionary = pd.DataFrame([
        ("timestamp", "", "Reading time, every 15 minutes"),
        ("outdoor_temp_c", "°C", "Outdoor air temperature (weather station)"),
        ("it_load_pct", "%", "Average CPU/GPU utilisation of all racks"),
        ("it_power_kw", "kW", "Power drawn by servers incl. their fans (UPS output meter)"),
        ("inlet_A1_c … inlet_B6_c", "°C", "Air temperature at the front (inlet) of each rack — the safety limit applies here"),
        ("supply_air_c", "°C", "Air temperature leaving the CRAH units"),
        ("return_air_c", "°C", "Hot-aisle air returning to the CRAH units"),
        ("crah_setpoint_c", "°C", "Supply-air setpoint commanded at this time — the one knob the AI controls"),
        ("crah_fan_pct", "%", "CRAH fan speed (automatic, follows IT load)"),
        ("chiller_kw / crah_fan_kw / pump_tower_kw", "kW", "Cooling sub-meters"),
        ("cooling_kw", "kW", "Total cooling power"),
        ("facility_kw", "kW", "Whole facility: IT + cooling + UPS losses + lighting"),
        ("pue", "", "facility_kw ÷ it_power_kw"),
    ], columns=["Column", "Unit", "Meaning"])
    st.dataframe(dictionary, hide_index=True, width="stretch")
    st.download_button("Download sensor_history.csv", C.DATA_PATH.read_bytes, "sensor_history.csv", "text/csv",
                       icon=":material/download:")
    st.dataframe(RAW.head(200), width="stretch", height=260)
