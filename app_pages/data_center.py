"""Data center: the live plant at one moment, the health of its 22 devices, flows, trends and installed models."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from predictive_cooling import config as C
from predictive_cooling.hardware import telemetry as hw_telemetry
from predictive_cooling.hardware.catalog import INSTALLED, INSTRUMENTS
from predictive_cooling.hardware.flows import balance
from predictive_cooling.hardware.gateway import point_table
from predictive_cooling.hardware.registry import DEVICES, REGISTRY, TRIPPABLE
from ui.common import (AXIS, CLEAN, CTRL, EQUIP, diagram, hardware_state, how_it_works, kpi, kpi_row, moment, page_header, show,
                       style)
from ui.panels import SEVERITY_BADGE, findings_frame
from ui.plant import KEY_POINTS, heat_sankey, plant_schematic, power_sankey, trends_figure

page_header("Data center", ":material/factory:", "The whole site at the moment picked in the sidebar: air, water and electricity, "
            "and what the 22 field devices say about their own health. Hover any unit for its installed model.", art="plant")
at = moment()
trips = st.pills("Simulate a trip", list(TRIPPABLE), selection_mode="multi", key="hw_trips",
                 help="The device stops (status 0) for the last 30 minutes; the health check should catch it")
snapshot, hw = hardware_state(str(at), tuple(trips or ()))
room, eq_row = CLEAN.loc[at] if at in CLEAN.index else None, EQUIP.loc[at] if at in EQUIP.index else None
complete = room is not None and eq_row is not None and not room[C.INLET_COLS + ["facility_kw"]].isna().any()
bal = balance(room, eq_row) if complete else None
health, _ = SEVERITY_BADGE[hw["overall"]]
cap = hw["capacity"]
kpi_row(kpi("PUE", f"{bal['kpi']['pue']:.2f}" if bal else "—", help="Facility power ÷ IT power"),
        kpi("Hottest inlet", f"{bal['kpi']['hottest_inlet_c']:.1f} °C" if bal else "—", "limit 27 °C"),
        kpi("Equipment health", health, f"{hw['devices_answering']} / {hw['devices_polled']} answering"),
        kpi("Cooling constraint", hw["constraint"].replace("_", " "),
            help="What the Hardware Engineer passes to safety rule R5: none · no raise (never warmer than now) · fallback"),
        kpi("N+1 capacity", f"{cap['n_minus_1_capacity_kw']:.0f} kW", f"week peak {cap['peak_it_kw_7d']:.0f} kW",
            help="If any one CRAH fails, can the other carry the highest IT load of the last 7 days?"))
if bal:
    show(plant_schematic(room, eq_row, bal))
else:
    st.warning("No complete room reading at this moment (logger gap). Pick another time.", icon=":material/signal_disconnected:")

if hw["findings"]:
    st.markdown("**What needs attention** · *constraint* is what the AI's safety check (rule R5) receives")
    st.dataframe(findings_frame(hw)[["Severity", "Device", "What", "Now", "Next limit", "Constraint", "Action"]],
                 hide_index=True, width="stretch")
else:
    st.success("All 22 devices are within their limits and N+1 cooling capacity holds.", icon=":material/check_circle:")

with how_it_works("Where the electricity and the heat go", icon=":material/account_tree:"):
    if bal:
        c1, c2 = st.columns(2)
        c1.plotly_chart(power_sankey(bal), width="stretch", config={"displayModeBar": False})
        c2.plotly_chart(heat_sankey(bal), width="stretch", config={"displayModeBar": False})
        st.caption("Electricity from the sub-meters and the rack PDUs; every kW the servers and fans use ends up in the chilled "
                   "water, and the cooling tower rejects it plus the chiller's own work.")

with how_it_works("Equipment trends: the faults hidden in the test weeks", icon=":material/monitoring:"):
    show(trends_figure(at))
    st.markdown("\n".join(f"- **{f['device']} · {f['code']}** (from {pd.Timestamp(f['start']):%d %b %H:%M}): {f['story']}"
                          for f in hw_telemetry.FAULTS))
    st.caption("Hourly means; the grey line is the moment in the sidebar. Limits come from ISO 10816-1 (vibration), ASHRAE "
               "(humidity) and the equipment datasheets; a straight line through the daily means projects days to the next limit.")

with how_it_works("Every device, and how the sensor gateway reads it", icon=":material/lan:"):
    plant = [d for d in DEVICES if d.kind != "pdu"]
    for start in range(0, len(plant), 5):
        for col, device in zip(st.columns(5), plant[start:start + 5]):
            reading = snapshot[device.id]
            with col.container(border=True, height="stretch"):
                if reading["comm"] != "ok":
                    tag, tag_color = "No answer", "gray"
                elif device.standby and reading["values"].get("status") == 0:
                    tag, tag_color = "Standby", "gray"
                else:
                    tag, tag_color = SEVERITY_BADGE[hw["device_health"][device.id]]
                st.markdown(f"**{device.id}** :{tag_color}-badge[{tag}]")
                lines = [f"{name} **{reading['values'][point]:g}** {device.point(point).unit}"
                         for point, name in KEY_POINTS[device.kind] if reading["values"].get(point) is not None]
                st.markdown("  \n".join(lines) or ":gray[—]")
    racks = pd.Series({r: snapshot[f"PDU-{r}"]["values"].get("power_kw") for r in C.RACKS}, dtype=float)
    fig = go.Figure(go.Bar(x=racks.index, y=racks.values, width=0.6,
                           marker_color=[CTRL["ai"] if C.RACK_ROLE[r] == "GPU" else AXIS for r in racks.index],
                           text=[f"{v:.1f}" for v in racks.values], textposition="outside", cliponaxis=False))
    fig.update_yaxes(title="kW", rangemode="tozero")
    show(style(fig, height=260, title=f"Rack power from the 12 PDUs · {racks.sum():.0f} kW (blue = GPU racks)", legend=False,
               hover="closest"))
    device_id = st.selectbox("One device's points on the wire", list(REGISTRY), index=list(REGISTRY).index("CRAH-2"),
                             format_func=lambda d: f"{d} · {REGISTRY[d].protocol} · {REGISTRY[d].endpoint}", key="hw_dev")
    st.dataframe(point_table(snapshot[device_id]), hide_index=True, width="stretch")
    diagram("""
flowchart LR
    D["22 field devices"]:::step --> P["BACnet/IP · Modbus TCP<br/>SNMP v3"]:::step --> GW["Sensor gateway<br/>raw → °C, kW, Pa + quality"]:::guard
    GW --> DX["Diagnostics<br/>limits · trends · N+1"]:::ai --> HE["Hardware Engineer"]:::agent
    HE -.->|"constraint"| R5["Safety rule R5"]:::guard
""", alt="Field devices, building protocols, sensor gateway, diagnostics, Hardware Engineer and safety rule R5")
    st.download_button("Download equipment_telemetry.csv", data=C.EQUIPMENT_PATH.read_bytes, file_name="equipment_telemetry.csv",
                       mime="text/csv", icon=":material/download:")

with how_it_works("Installed models and instruments", icon=":material/inventory_2:"):
    link = {"Source": st.column_config.LinkColumn(display_text="datasheet / page")}
    bom = pd.DataFrame([{"Device": d.id, "Installed model": (p.vendor + " · " if p.vendor != "—" else "") + p.model,
                         "Facts used": p.facts, "Protocol": d.protocol, "Note": p.note, "Source": p.source or None}
                        for d in DEVICES if d.kind != "pdu" for p in [INSTALLED[d.id]]]
                       + [{"Device": "PDU-A1 … B6", "Installed model": "Raritan (Legrand) · PX3", "Facts used": INSTALLED["PDU-A1"].facts,
                           "Protocol": "SNMP v3", "Note": INSTALLED["PDU-A1"].note, "Source": INSTALLED["PDU-A1"].source}])
    st.dataframe(bom, hide_index=True, width="stretch", column_config=link)
    st.dataframe(pd.DataFrame([{"Measures": what, "Instrument": f"{p.vendor} · {p.model}", "Facts used": p.facts,
                                "Source": p.source} for what, p in INSTRUMENTS]), hide_index=True, width="stretch", column_config=link)
    st.caption("Real product families with the vendor-published facts used here (checked Nov 2026); 'class' rows describe a legacy "
               "unit without naming a model. The plant model's own numbers are this project's, not datasheet values.")
