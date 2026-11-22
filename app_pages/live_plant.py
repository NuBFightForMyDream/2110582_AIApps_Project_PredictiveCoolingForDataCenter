"""Live plant: the whole site at one moment, with its flows and installed equipment."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.colors import sample_colorscale

from predictive_cooling import config as C
from predictive_cooling.hardware.catalog import INSTALLED, INSTRUMENTS
from predictive_cooling.hardware.flows import balance
from predictive_cooling.hardware.registry import DEVICES, REGISTRY
from ui.common import AXIS, CLEAN, EQUIP, FONT, INK, INK2, MUTED, SURFACE, moment, page_header, show, style


FLOW = {"chw_supply": "#2a78d6", "chw_return": "#d03b3b", "condenser": "#eb6834", "power": "#6250d6",
        "cold": "#6da7ec", "hot": "#ec8a89"}
RACK_SCALE = [[0.0, "#184f95"], [0.25, "#6da7ec"], [0.5, "#f0efec"], [0.75, "#ec8a89"], [1.0, "#a82e2e"]]


def _hover(device_id, extra=""):
    product = INSTALLED.get(device_id)
    text = f"<b>{device_id}</b>"
    if product:
        text += f"<br>{product.vendor + ' · ' if product.vendor != '—' else ''}{product.model}<br>{product.facts}"
    if device_id in REGISTRY:
        text += f"<br>{REGISTRY[device_id].protocol} · {REGISTRY[device_id].endpoint}"
    return text + (f"<br>{extra}" if extra else "")


def plant_schematic(room, eq, bal):
    """A one-page plant drawing: plant room + roof (left), data hall (right), electrical room (bottom), live values."""
    fig = go.Figure()
    hover_x, hover_y, hover_t = [], [], []

    def zone(x0, y0, x1, y1, label, fill="#f6f6f3"):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1, fillcolor=fill, line=dict(color=AXIS, width=1), layer="below")
        fig.add_annotation(x=x0 + 0.8, y=y1 - 0.6, text=f"<b>{label}</b>", xanchor="left", yanchor="top", showarrow=False,
                           font=dict(size=11, color=INK2))

    def box(x0, y0, x1, y1, text, hover, fill="white", line=INK2, size=10.5, color=INK):
        fig.add_shape(type="rect", x0=x0, y0=y0, x1=x1, y1=y1, fillcolor=fill, line=dict(color=line, width=1.4))
        fig.add_annotation(x=(x0 + x1) / 2, y=(y0 + y1) / 2, text=text, showarrow=False, font=dict(size=size, color=color))
        hover_x.append((x0 + x1) / 2), hover_y.append((y0 + y1) / 2), hover_t.append(hover)

    def pipe(points, color, width=3.2, dash=None):
        xs, ys = zip(*points)
        fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color=color, width=width, dash=dash), hoverinfo="skip", showlegend=False)

    def arrow(x0, y0, x1, y1, color, width=2.0, text=""):
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y", showarrow=True, arrowhead=3,
                           arrowsize=1.1, arrowwidth=width, arrowcolor=color, text=text, font=dict(size=10, color=color))

    def label(x, y, text, color=INK2, size=10, anchor="center"):
        fig.add_annotation(x=x, y=y, text=text, showarrow=False, font=dict(size=size, color=color), xanchor=anchor)

    v = lambda d, p: float(eq[f"{d}.{p}"])  # noqa: E731
    zone(1, 45, 25, 63, "Roof")
    zone(1, 16, 25, 41, "Plant room")
    zone(29, 16, 99, 63, "Data hall · 2 rows × 6 racks")
    zone(29, 1, 99, 13, "Electrical room")
    zone(1, 1, 25, 13, "Utility")
    fig.add_shape(type="rect", x0=40, y0=55.5, x1=98, y1=61.8, fillcolor="#fbeeee", line_width=0, layer="below")
    fig.add_shape(type="rect", x0=40, y0=34, x1=98, y1=47, fillcolor="#e8f1fc", line_width=0, layer="below")
    fig.add_shape(type="rect", x0=40, y0=18.2, x1=98, y1=25, fillcolor="#fbeeee", line_width=0, layer="below")
    label(69, 60.4, "hot aisle", FLOW["chw_return"])
    label(69, 45.5, f"cold aisle · over-pressure {v('ENV-DP-1', 'aisle_dp_pa'):.1f} Pa · RH {v('ENV-CA-1', 'rh_pct'):.0f} %",
          FLOW["chw_supply"])
    label(69, 19.5, "hot aisle", FLOW["chw_return"])

    # racks, coloured by inlet temperature
    for row, y0 in (("A", 48), ("B", 26)):
        for i, rack in enumerate(C.ROWS[row]):
            x0 = 41.5 + i * 9.3
            inlet = float(room[f"inlet_{rack}_c"])
            share = min(max((inlet - 18) / 10, 0), 1)
            fill = sample_colorscale(RACK_SCALE, [share])[0]
            dark = inlet < 20.5 or inlet > 25.5
            box(x0, y0, x0 + 7.5, y0 + 7, f"<b>{rack}</b><br>{inlet:.1f} °C<br>{bal['power']['racks'][rack]:.1f} kW",
                _hover(f"PDU-{rack}", f"{C.RACK_ROLE[rack]} rack · inlet sensor {INSTRUMENTS[0][1].model} ({INSTRUMENTS[0][1].facts})"),
                fill=fill, line=AXIS, size=9.5, color="white" if dark else INK)
            xc = x0 + 3.75
            arrow(xc, 46.6 if row == "A" else 34.4, xc, 57.5 if row == "A" else 23.5, FLOW["hot"], width=1.2)

    # CRAH units and air paths
    for unit, (y0, y1) in (("CRAH-1", (46, 58)), ("CRAH-2", (21, 33))):
        box(31, y0, 37.8, y1, f"<b>{unit}</b><br>supply {v(unit, 'supply_air_c'):.1f} °C<br>fan {v(unit, 'fan_speed_pct'):.0f} %"
            f"<br>filter {v(unit, 'filter_dp_pa'):.0f} Pa", _hover(unit, f"airflow {v(unit, 'airflow_m3h'):,.0f} m³/h · "
                                                                     f"{v(unit, 'fan_kw'):.1f} kW"), fill="#eef5fd", line=FLOW["chw_supply"])
    arrow(37.8, 52, 42, 43.5, FLOW["cold"], 2.4)
    arrow(37.8, 27, 42, 37, FLOW["cold"], 2.4)
    arrow(44, 40.5, 96, 40.5, FLOW["cold"], 2.4, "")
    label(70, 38.2, "cold supply air → rack fronts", FLOW["chw_supply"], 10)
    arrow(97, 59, 38.6, 57.4, FLOW["hot"], 2.4)
    arrow(97, 21.4, 38.6, 22.8, FLOW["hot"], 2.4)
    arrow(97.6, 24, 97.6, 36.5, FLOW["chw_return"], 2.0, "")
    label(97.3, 30, "recirc.", FLOW["chw_return"], 9.5, "right")

    # chilled water: chiller -> CRAH coils -> pump -> chiller
    box(3, 26, 14.5, 37.5, f"<b>CH-1 chiller</b><br>COP {bal['kpi']['cop']:.1f} · {bal['power']['chiller']:.0f} kW<br>"
        f"load {bal['kpi']['load_pct']:.0f} %", _hover("CH-1", f"condenser approach {v('CH-1', 'cond_approach_c'):.2f} °C"),
        fill="#eef5fd", line=FLOW["chw_supply"])
    pipe([(14.5, 34.5), (26, 34.5), (26, 52), (31, 52)], FLOW["chw_supply"])
    pipe([(26, 34.5), (26, 27), (31, 27)], FLOW["chw_supply"])
    pipe([(31, 49.5), (27.6, 49.5), (27.6, 24.5), (31, 24.5)], FLOW["chw_return"])
    pipe([(27.6, 30.5), (22.2, 30.5)], FLOW["chw_return"])
    pipe([(17.8, 30.5), (14.5, 30.5)], FLOW["chw_return"])
    label(19.5, 36, f"CHW supply {v('CH-1', 'chws_c'):.1f} °C", FLOW["chw_supply"], 9.5)
    label(19.5, 28.4, f"return {v('CH-1', 'chwr_c'):.1f} °C", FLOW["chw_return"], 9.5)
    for pump, y in (("CHWP-1", 30.5), ("CHWP-2", 21)):
        running = v(pump, "status") == 1
        fig.add_shape(type="circle", x0=17.8, y0=y - 2.1, x1=22.2, y1=y + 2.1, fillcolor="white" if running else "#f0efec",
                      line=dict(color=FLOW["chw_return"] if running else AXIS, width=1.6))
        hover_x.append(20), hover_y.append(y)
        hover_t.append(_hover(pump, f"{'running' if running else 'standby'} · {v(pump, 'flow_m3h'):.1f} m³/h · "
                                    f"vibration {v(pump, 'vibration_mm_s'):.2f} mm/s · flow meter {INSTRUMENTS[2][1].model}"))
        label(20, y - 3.4, f"{pump}{'' if running else ' (standby)'}", INK2, 9)

    # condenser water: chiller <-> tower
    if pd.notna(eq["CT-1.fan_speed_pct"]):
        box(4, 49, 21.5, 59.5, f"<b>CT-1 cooling tower</b><br>fan {v('CT-1', 'fan_speed_pct'):.0f} % · approach "
            f"{v('CT-1', 'approach_c'):.1f} °C<br>wet bulb {v('CT-1', 'wet_bulb_c'):.1f} °C · outdoor "
            f"{float(room['outdoor_temp_c']):.1f} °C", _hover("CT-1"), fill="#fdf1ea", line=FLOW["condenser"])
    else:
        box(4, 49, 21.5, 59.5, "<b>CT-1 cooling tower</b><br>no answer (comm loss)", _hover("CT-1"), fill="#f0efec", line=AXIS)
    pipe([(7, 37.5), (7, 49)], FLOW["condenser"])
    pipe([(11.5, 49), (11.5, 37.5)], "#f3b08e")
    arrow(7, 41, 7, 46.5, FLOW["condenser"], 2.0)
    arrow(11.5, 46.5, 11.5, 41, "#f3b08e", 2.0)
    label(16.5, 43.5, f"condenser {v('CH-1', 'cond_out_c'):.1f} → {v('CH-1', 'cond_in_c'):.1f} °C", FLOW["condenser"], 9.5)

    # electricity
    box(3, 3, 22, 11.5, f"<b>Grid</b><br>facility {bal['power']['facility']:.0f} kW · PUE {bal['kpi']['pue']:.2f}",
        "<b>Utility supply</b><br>facility meter: " + INSTRUMENTS[1][1].model, fill="white", line=FLOW["power"])
    box(33, 3, 47, 11.5, f"<b>UPS-1</b><br>{v('UPS-1', 'load_pct'):.0f} % · {v('UPS-1', 'output_kw'):.0f} kW",
        _hover("UPS-1", f"battery {v('UPS-1', 'battery_temp_c'):.0f} °C · efficiency {v('UPS-1', 'efficiency_pct'):.1f} %"),
        fill="#f1effc", line=FLOW["power"])
    pipe([(22, 7.2), (33, 7.2)], FLOW["power"], 2.6)
    pipe([(47, 7.2), (96, 7.2)], FLOW["power"], 2.6)
    for xc in (52, 70, 88):
        pipe([(xc, 7.2), (xc, 18.2)], FLOW["power"], 1.6, "dot")
    label(72, 9.6, f"→ 12 rack PDUs ({INSTALLED['PDU-A1'].model}) · IT {bal['power']['it']:.0f} kW", FLOW["power"], 10)
    pipe([(12.5, 11.5), (12.5, 26)], FLOW["power"], 1.8, "dot")
    label(13.4, 14.5, f"cooling {bal['power']['chiller'] + bal['power']['crah_fans'] + bal['power']['pumps_tower']:.0f} kW",
          FLOW["power"], 9.5, "left")

    fig.add_scatter(x=hover_x, y=hover_y, mode="markers", marker=dict(size=26, color="rgba(0,0,0,0)"), hovertext=hover_t,
                    hoverinfo="text", showlegend=False)
    for name, color, dash in [("Chilled water supply", FLOW["chw_supply"], None), ("Chilled water return", FLOW["chw_return"], None),
                              ("Condenser water", FLOW["condenser"], None), ("Electricity", FLOW["power"], None),
                              ("Cold air", FLOW["cold"], None), ("Hot air", FLOW["hot"], None)]:
        fig.add_scatter(x=[None], y=[None], mode="lines", line=dict(color=color, width=3, dash=dash), name=name)
    fig.update_xaxes(visible=False, range=[0, 100])
    fig.update_yaxes(visible=False, range=[0, 64])
    return style(fig, height=640, title=None, hover="closest")


def sankey(labels, colors, links, title):
    src, dst, val, col = zip(*links)
    fig = go.Figure(go.Sankey(
        arrangement="snap", valueformat=".1f", valuesuffix=" kW",
        node=dict(label=labels, color=colors, pad=14, thickness=14, line=dict(color=SURFACE, width=1)),
        link=dict(source=src, target=dst, value=[max(x, 0.01) for x in val], color=col)))
    fig.update_layout(height=360, margin=dict(l=8, r=8, t=40, b=8), title=dict(text=title, font=dict(size=15, color=INK)),
                      font=dict(family=FONT, size=12, color=INK2), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def power_sankey(bal):
    pw = bal["power"]
    groups = list(pw["groups"])
    labels = [f"Grid {pw['facility']:.0f} kW", "UPS-1", *groups, "UPS losses", "Chiller", "CRAH fans", "Pumps + tower", "Lighting"]
    colors = [INK2, FLOW["power"], "#2a78d6", "#86b6ef", "#184f95", MUTED, FLOW["condenser"], "#eda100", "#f3b08e", AXIS]
    soft = lambda c: c + "66"  # noqa: E731
    links = [(0, 1, pw["it"] + pw["ups_loss"], soft(FLOW["power"]))]
    links += [(1, 2 + i, pw["groups"][g], soft("#2a78d6")) for i, g in enumerate(groups)]
    links += [(1, 5, pw["ups_loss"], soft(MUTED)), (0, 6, pw["chiller"], soft(FLOW["condenser"])),
              (0, 7, pw["crah_fans"], soft("#eda100")), (0, 8, pw["pumps_tower"], soft("#f3b08e")), (0, 9, pw["lighting"], soft(AXIS))]
    return sankey(labels, colors, links, "Where the electricity goes")


def heat_sankey(bal):
    h = bal["heat"]
    labels = ["Servers (IT)", "CRAH fans", "Walls (outdoor heat)", f"Chilled water {h['chilled_water']:.0f} kW",
              "Chiller compressor", "Condenser water", "Cooling tower", f"Outdoor air {h['rejected']:.0f} kW"]
    colors = ["#2a78d6", "#eda100", MUTED, FLOW["chw_supply"], FLOW["condenser"], FLOW["condenser"], "#f3b08e", INK2]
    links = [(0, 3, h["it"], "#2a78d666"), (1, 3, h["crah_fans"], "#eda10066"), (2, 3, h["walls"], "#89878166"),
             (3, 5, h["chilled_water"], "#2a78d666"), (4, 5, h["compressor"], "#eb683466"), (5, 6, h["rejected"], "#eb683466"),
             (6, 7, h["rejected"], "#f3b08e88")]
    return sankey(labels, colors, links, "Where the heat goes")


page_header("Live plant", ":material/factory:", "The whole site at one moment: air, water and electricity, with the "
            "installed model of every unit.",
            ["**Air**: CRAH → cold aisle → racks → hot aisle. **Chilled water**: chiller → CRAH coils → pumps. **Condenser "
             "water**: chiller → cooling tower. **Electricity**: grid → UPS → rack PDUs.",
             "Hover any unit for its installed model, protocol and live points.",
             "Two Sankey diagrams answer *where does the electricity go?* and *where does the heat go?*"], art="plant")
dc_at = moment()
room, eq_row = CLEAN.loc[dc_at] if dc_at in CLEAN.index else None, EQUIP.loc[dc_at] if dc_at in EQUIP.index else None
if room is None or eq_row is None or room[C.INLET_COLS + ["facility_kw"]].isna().any():
    st.warning("No complete reading at this moment (logger gap). Pick another time.")
else:
    bal = balance(room, eq_row)
    k = st.columns(5)
    k[0].metric("PUE", f"{bal['kpi']['pue']:.2f}", border=True, help="Facility power ÷ IT power")
    k[1].metric("Cooling per IT kW", f"{bal['kpi']['cooling_per_it']:.2f}", border=True,
                help="Cooling power ÷ IT power: the part of PUE the AI and the upgrades attack")
    k[2].metric("Chiller", f"{bal['kpi']['kw_per_tr']:.2f} kW/TR", border=True,
                help=f"COP {bal['kpi']['cop']:.2f}; 1 TR = 3.517 kW of cooling")
    k[3].metric("Chilled-water ΔT", f"{bal['kpi']['chw_delta_c']:.1f} °C", border=True,
                help="Return − supply; a low ΔT means pumping more water than the load needs")
    k[4].metric("Hottest inlet", f"{bal['kpi']['hottest_inlet_c']:.1f} °C", border=True, help="ASHRAE recommended ≤ 27 °C")
    show(plant_schematic(room, eq_row, bal))
    st.caption(f"{dc_at:%a %d %b %H:%M}. Arrows show direction; rack colour = inlet temperature (blue cool → red hot); the red "
               "arrow at the row end is hot air recirculating around B6, the hot spot that containment fixes.")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(power_sankey(bal), width="stretch", config={"displayModeBar": False})
    with c2:
        st.plotly_chart(heat_sankey(bal), width="stretch", config={"displayModeBar": False})
    st.caption("Electricity from the sub-meters (PowerLogic PM5560) and the rack PDUs; heat from the same balance: every kW "
               "the servers and fans use ends up in the chilled water, and the tower rejects it plus the chiller's own work.")

st.subheader("Installed equipment and the instruments that measure it", icon=":material/inventory_2:")
bom = pd.DataFrame([{"Device": d.id, "Role": d.name, "Installed model": (p.vendor + " · " if p.vendor != "—" else "") + p.model,
                     "Facts used": p.facts, "Protocol": d.protocol, "Note": p.note, "Source": p.source or None}
                    for d in DEVICES if d.kind != "pdu" for p in [INSTALLED[d.id]]]
                   + [{"Device": "PDU-A1 … B6", "Role": "12 rack PDUs", "Installed model": "Raritan (Legrand) · PX3",
                       "Facts used": INSTALLED["PDU-A1"].facts, "Protocol": "SNMP v3", "Note": INSTALLED["PDU-A1"].note,
                       "Source": INSTALLED["PDU-A1"].source}])
link = {"Source": st.column_config.LinkColumn(display_text="datasheet / page")}
st.dataframe(bom, hide_index=True, width="stretch", column_config=link)
st.dataframe(pd.DataFrame([{"Measures": what, "Instrument": f"{p.vendor} · {p.model}", "Facts used": p.facts, "Note": p.note,
                            "Source": p.source} for what, p in INSTRUMENTS]), hide_index=True, width="stretch", column_config=link)
st.caption("Named products are real product families with the vendor-published facts this project relies on (checked Nov 2026); "
           "'class' rows describe a legacy unit without naming a model. The plant model's numbers (capacity, COP, fan power) are "
           "this project's own, not datasheet values. Setra lists the Model 264 as discontinued: the advisor would plan a replacement.")
