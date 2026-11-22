"""Equipment health: the 22 field devices, their findings and the sensor gateway."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from predictive_cooling import config as C
from predictive_cooling.hardware import telemetry as hw_telemetry
from predictive_cooling.hardware.diagnostics import RULES as HW_RULES, metrics
from predictive_cooling.hardware.gateway import point_table
from predictive_cooling.hardware.registry import CRAH_RATED_AIRFLOW_M3H, CRAH_RATED_KW, DEVICES, REGISTRY, TRIPPABLE
from ui.common import (AXIS, CRIT, CTRL, EQUIP, INK2, MUTED, QTY, WARN, diagram, hardware_state, how_it_works, hw_limit, kpi, kpi_row,
                       moment, page_header, show, style)
from ui.panels import SEVERITY_BADGE, findings_frame


KEY_POINTS = {
    "crah": [("supply_air_c", "Supply"), ("fan_speed_pct", "Fan"), ("filter_dp_pa", "Filter ΔP")],
    "chiller": [("load_pct", "Load"), ("cop", "COP"), ("cond_approach_c", "Cond. approach")],
    "pump": [("flow_m3h", "Flow"), ("vibration_mm_s", "Vibration"), ("bearing_temp_c", "Bearing")],
    "cooling_tower": [("fan_speed_pct", "Fan"), ("wet_bulb_c", "Wet bulb"), ("approach_c", "Approach")],
    "ups": [("load_pct", "Load"), ("output_kw", "Output"), ("battery_temp_c", "Battery")],
    "env": [("temp_c", "Temp"), ("rh_pct", "RH"), ("aisle_dp_pa", "Over-pressure")],
}
HW_FROM = "2026-04-06"              # trend panels: two weeks of build-up, then the test weeks


@st.cache_data(show_spinner=False)
def hardware_trends():
    """Hourly series of the metrics the diagnostics use, for the trend panels."""
    pdu = EQUIP[[REGISTRY[f"PDU-{r}"].column("power_kw") for r in C.RACKS]].sum(axis=1, min_count=len(C.RACKS))
    peak7 = pdu.rolling("7D").max()
    frame = EQUIP.loc[HW_FROM:]
    out = pd.DataFrame(index=frame.index)
    for u in (1, 2):
        crah = REGISTRY[f"CRAH-{u}"]
        speed = frame[crah.column("fan_speed_pct")] / 100
        out[f"filter_{u}"] = metrics(frame, crah)["filter_dp_100_pa"]
        out[f"cap_{u}"] = CRAH_RATED_KW * (frame[crah.column("airflow_m3h")] / (CRAH_RATED_AIRFLOW_M3H * speed)).clip(0.5, 1.0)
    out["vibration"] = frame["CHWP-1.vibration_mm_s"]
    out["approach"] = frame["CH-1.cond_approach_c"]
    for sensor in ("ENV-CA-1", "ENV-CA-2"):
        out[sensor] = metrics(frame, REGISTRY[sensor])["rh_deviation_pct"]
    out["peak7"] = peak7.loc[HW_FROM:]
    out["dp"] = frame["ENV-DP-1.aisle_dp_pa"]
    return out.resample("1h").mean()


def rule_limits(code):
    rule = next(r for r in HW_RULES if r.code == code)
    return rule.warning, rule.critical


page_header("Equipment health", ":material/memory:", "What the equipment itself says: 22 field devices, read every 15 minutes.",
            [f"**{len(DEVICES)} devices** (2 CRAH units, a chiller, 2 pumps, a cooling tower, the UPS, 3 room sensors, 12 rack "
             "PDUs) are polled over **BACnet/IP, Modbus TCP and SNMP v3**; the sensor gateway flags values it cannot trust.",
             "The **Hardware Engineer** agent checks limits (ISO 10816 vibration, ASHRAE humidity, filter ΔP), projects 7-day "
             "trends to *days until the next limit* and checks **N+1** cooling capacity.",
             "A cooling-equipment problem stops the AI from running the room warmer (rule **R5**). Try *Hardware warnings* in the "
             "sidebar, or simulate a trip."], art="hardware")
with how_it_works("From a device register to an agent's finding"):
    diagram("""
    flowchart LR
    D["22 field devices<br/>CRAH · chiller · pumps · tower<br/>UPS · room sensors · PDUs"]:::step --> P["BACnet/IP<br/>Modbus TCP · SNMP v3"]:::step
    P --> GW["Sensor gateway<br/>raw register → °C, kW, Pa<br/>+ quality flag"]:::guard
    GW --> H[("Historian<br/>15-min, 7 days")]:::step
    GW --> DX["Diagnostics<br/>limits · trends · N+1"]:::ai
    H --> DX
    DX --> HE["Hardware Engineer<br/>(skill S6)"]:::agent
    HE --> SUP["Supervisor"]:::agent
    HE -.->|"cooling constraint"| R5["Safety rule R5<br/>no warmer than now"]:::guard
    """, alt="Hardware layer: field devices, building protocols, sensor gateway, historian, diagnostics, Hardware Engineer, Supervisor and safety rule R5")
hw_at = moment()
hw_trips = st.pills("Simulate a trip", list(TRIPPABLE), selection_mode="multi", key="hw_trips",
                    help="The device stops (status 0) for the last 30 minutes")
snapshot, hw = hardware_state(str(hw_at), tuple(hw_trips or ()))
cap = hw["capacity"]
label, color = SEVERITY_BADGE[hw["overall"]]
kpi_row(kpi("Devices answering", f"{hw['devices_answering']} / {hw['devices_polled']}",
            help="A device that does not answer its poll is unknown, not healthy"),
        kpi("Equipment health", label),
        kpi("Cooling constraint", hw["constraint"].replace("_", " "),
            help="none · no raise (never warmer than now) · fallback (never warmer than the proven setpoint)"),
        kpi("N+1 capacity", f"{cap['n_minus_1_capacity_kw']:.0f} kW", f"week peak {cap['peak_it_kw_7d']:.0f} kW",
            help="If any one CRAH fails, can the other carry the highest IT load of the last 7 days?"),
        kpi("Findings", f"{len(hw['findings'])}"))

st.markdown(f"**Devices at {hw_at:%a %d %b %H:%M}**")
plant = [d for d in DEVICES if d.kind != "pdu"]
for start in range(0, len(plant), 5):
    cols = st.columns(5)
    for col, device in zip(cols, plant[start:start + 5]):
        reading = snapshot[device.id]
        with col.container(border=True, height="stretch"):
            if reading["comm"] != "ok":
                tag, tag_color = "No answer", "gray"
            elif device.standby and reading["values"].get("status") == 0:
                tag, tag_color = "Standby", "gray"
            else:
                tag, tag_color = SEVERITY_BADGE[hw["device_health"][device.id]]
            st.markdown(f"**{device.id}** :{tag_color}-badge[{tag}]")
            st.caption(f"{device.name} · {device.protocol}")
            lines = [f"{name} **{reading['values'][point]:g}** {device.point(point).unit}"
                     for point, name in KEY_POINTS[device.kind] if reading["values"].get(point) is not None]
            st.markdown("  \n".join(lines) or ":gray[—]")

if hw["findings"]:
    st.markdown("**Findings** — sorted by severity; *constraint* is what the Cooling Advisor's safety check (R5) receives")
    st.dataframe(findings_frame(hw), hide_index=True, width="stretch",
                 column_config={"Basis": st.column_config.TextColumn(width="large"),
                                "Action": st.column_config.TextColumn(width="medium")})
else:
    st.success("All 22 devices are within their limits and N+1 cooling capacity holds.", icon=":material/check_circle:")

trend = hardware_trends()
fig = make_subplots(rows=3, cols=2, shared_xaxes=True, vertical_spacing=0.1, horizontal_spacing=0.08,
                    subplot_titles=("CRAH filter ΔP at 100 % fan (Pa)", "CHWP-1 vibration (mm/s RMS)",
                                    "CH-1 condenser approach (°C)", "Humidity sensor vs CRAH reference (|Δ| %RH)",
                                    "N+1: one CRAH's capacity vs week-peak IT (kW)", "Cold-aisle over-pressure (Pa)"))
fig.add_scatter(x=trend.index, y=trend["filter_1"], name="CRAH-1", line=dict(color=MUTED, width=1.6), row=1, col=1)
fig.add_scatter(x=trend.index, y=trend["filter_2"], name="CRAH-2", line=dict(color=CTRL["ai"], width=2), row=1, col=1)
fig.add_scatter(x=trend.index, y=trend["vibration"], name="CHWP-1", line=dict(color=CTRL["ai"], width=2), row=1, col=2,
                showlegend=False)
fig.add_scatter(x=trend.index, y=trend["approach"], name="CH-1", line=dict(color=CTRL["ai"], width=2), row=2, col=1,
                showlegend=False)
fig.add_scatter(x=trend.index, y=trend["ENV-CA-1"], name="ENV-CA-1", line=dict(color=MUTED, width=1.6), row=2, col=2)
fig.add_scatter(x=trend.index, y=trend["ENV-CA-2"], name="ENV-CA-2", line=dict(color=QTY["temp"], width=2), row=2, col=2)
fig.add_scatter(x=trend.index, y=trend["cap_2"], name="CRAH-2 capacity", line=dict(color=CTRL["ai"], width=2), row=3, col=1)
fig.add_scatter(x=trend.index, y=trend["peak7"], name="Week-peak IT load", line=dict(color=QTY["it"], width=2, shape="hv"),
                row=3, col=1)
fig.add_scatter(x=trend.index, y=trend["dp"], name="ENV-DP-1", line=dict(color=CTRL["ai"], width=2), row=3, col=2,
                showlegend=False)
for code, row, col in [("FILTER_LOADING", 1, 1), ("BEARING_WEAR", 1, 2), ("CONDENSER_FOULING", 2, 1), ("SENSOR_DRIFT", 2, 2)]:
    warning, critical = rule_limits(code)
    hw_limit(fig, warning, row, col, f"warning {warning:g}", WARN)
    if code in ("BEARING_WEAR", "CONDENSER_FOULING"):
        hw_limit(fig, critical, row, col, f"critical {critical:g}", CRIT)
hw_limit(fig, rule_limits("CONTAINMENT_PRESSURE")[0], 3, 2, "warning 1", WARN)
fig.add_vline(x=hw_at, line=dict(color=INK2, width=1))
show(style(fig, height=640, title="Four faults hidden in the equipment data, seen days before any rack gets hot"))
st.caption("Hourly means. The room-level sensor log shows none of this yet — that is why the hardware is watched directly. "
           "The grey line marks the moment picked above.")

c1, c2 = st.columns([1, 1.25])
with c1:
    racks = pd.Series({r: snapshot[f"PDU-{r}"]["values"].get("power_kw") for r in C.RACKS}, dtype=float)
    fig = go.Figure(go.Bar(x=racks.index, y=racks.values, width=0.6,
                           marker_color=[CTRL["ai"] if C.RACK_ROLE[r] == "GPU" else AXIS for r in racks.index],
                           text=[f"{v:.1f}" for v in racks.values], textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}: %{y:.2f} kW<extra></extra>"))
    fig.update_yaxes(title="kW", rangemode="tozero")
    show(style(fig, height=300, title=f"Rack power from the 12 PDUs · {racks.sum():.0f} kW", legend=False, hover="closest"))
    st.caption("Blue = GPU racks B4–B6. The PDUs (SNMP) give the IT load per rack; the N+1 check uses their sum.")
with c2:
    device_id = st.selectbox("Gateway view: one device's points", list(REGISTRY), index=list(REGISTRY).index("CRAH-2"),
                             format_func=lambda d: f"{d} · {REGISTRY[d].protocol} · {REGISTRY[d].endpoint}", key="hw_dev")
    st.dataframe(point_table(snapshot[device_id]), hide_index=True, width="stretch")
    st.caption("Raw value = what the protocol carries (BACnet REAL, Modbus 16-bit register × scale, SNMP integer). "
               "The gateway decodes it and checks the physical range before anything downstream sees it.")

with st.expander("Faults hidden in the equipment data, and how the file is made", icon=":material/description:"):
    st.markdown("\n".join(f"- **{f['device']} · {f['code']}** (from {pd.Timestamp(f['start']):%d %b %H:%M}): {f['story']}"
                          for f in hw_telemetry.FAULTS))
    st.caption("data/equipment_telemetry.csv is the equipment historian: 69 points from 22 devices every "
                "15 minutes, derived from the same plant run as sensor_history.csv (same seeds, so temperatures and power "
                "agree), plus chilled/condenser-water temperatures, pump flow, filter ΔP, humidity, containment pressure and "
                "per-rack PDU power. Rebuild it with `python -m predictive_cooling.hardware`.")
    st.download_button("Download equipment_telemetry.csv", data=C.EQUIPMENT_PATH.read_bytes, file_name="equipment_telemetry.csv",
                       mime="text/csv", icon=":material/download:")
