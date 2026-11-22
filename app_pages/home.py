"""Overview: the project on one page, with a door to every part of it."""
import streamlit as st

from predictive_cooling.hardware import advisor as hw_advisor
from ui.common import B, HEAD, diagram, how_it_works, kpi, kpi_row, signed

ai = HEAD["ai"]
summary = B["summary"].set_index(["scenario", "key"])
blind = summary.loc[("spoofing_attack", "ai_no_integrity"), "violation_minutes"]
guarded = summary.loc[("spoofing_attack", "ai"), "violation_minutes"]
package = next(o for o in hw_advisor.plan(B["upgrades"])["options"] if o["key"] == "package")

left, right = st.columns([1.2, 1], gap="large", vertical_alignment="center")
with left:
    st.title("Predictive cooling for a data center", icon=":material/ac_unit:")
    st.markdown("Server rooms waste electricity by cooling more than they need. This project **forecasts the next hour** and "
                "picks the warmest cooling setpoint that still keeps every rack below **27 °C**. Five AI agents check the "
                "data, the equipment and the options first, and explain the decision.")
    with st.container(horizontal=True):
        st.page_link("app_pages/agents.py", label="Ask the agents", icon=":material/smart_toy:")
        st.page_link("app_pages/live_plant.py", label="See the live plant", icon=":material/factory:")
        st.page_link("app_pages/results.py", label="See the results", icon=":material/bolt:")
with right:
    st.image("CoverPage.png", width="stretch", alt="Cover: a cooling unit blows cold air through server racks while a friendly "
             "robot watches a forecast chart")
kpi_row(kpi("Cooling energy", signed(-HEAD["rule"]["cooling_pct"]), "vs tuned rule",
            help="AI vs a tuned rule-based controller, two test weeks the AI never trained on"),
        kpi("Minutes > 27 °C", f"{ai['violation_minutes']:.0f}", "two test weeks"),
        kpi("Under attack", f"{guarded:.0f} min", f"{blind:.0f} unchecked",
            help=f"Minutes above 27 °C when an attacker forges the GPU racks' readings: {guarded:.0f} with the integrity "
                 f"check, {blind:.0f} without it"),
        kpi("All upgrades", f"−{package['saved_facility_pct']:.1f} %", "facility energy",
            help="Every hardware option together, with the AI, measured in closed loop (Upgrade advisor)"))
st.caption("All data is a mock 12-rack room from a physics model. Nothing here controls real equipment.")

st.subheader("The idea in 30 seconds", icon=":material/lightbulb:")
cols = st.columns(3)
for col, (icon, head, body) in zip(cols, [
    (":material/thermostat:", "The problem",
     "Cooling runs at a safe but cold setpoint all day. Colder than needed means wasted electricity."),
    (":material/insights:", "The idea",
     "Every 15 minutes: forecast the next hour, test **81 setpoint plans**, keep only the safe ones, pick the cheapest."),
    (":material/verified_user:", "The result",
     f"**{HEAD['rule']['cooling_pct']:.1f} % less cooling energy** than a tuned rule and **{ai['violation_minutes']:.0f} minutes** "
     "above 27 °C, with six safety rules that can always override the AI."),
]):
    with col.container(border=True, height="stretch"):
        st.markdown(f"{icon} **{head}**")
        st.markdown(body)

st.subheader("Every 15 minutes", icon=":material/autorenew:")
steps = [
    ("app_pages/sensors.py", ":material/sensors:", "1 · Sensors", "12 rack inlets, power meters, cooling units and weather."),
    ("app_pages/cleaning.py", ":material/cleaning_services:", "2 · Clean", "Gaps, glitches and stuck sensors are fixed first."),
    ("app_pages/forecast.py", ":material/insights:", "3 · Forecast", "Machine learning predicts the next hour for any plan."),
    ("app_pages/mpc.py", ":material/route:", "4 · Plan", "81 plans tried; unsafe ones dropped; the cheapest wins."),
    ("app_pages/safety.py", ":material/shield:", "5 · Safety", "Six rules check every command before it is sent."),
    ("app_pages/results.py", ":material/bolt:", "6 · Results", "The simulated room scores energy and overheating."),
]
for row in (steps[:3], steps[3:]):
    for col, (page, icon, head, body) in zip(st.columns(3), row):
        with col.container(border=True, height="stretch"):
            st.markdown(f"{icon} **{head}**")
            st.caption(body)
            st.page_link(page, label="Open", icon=":material/arrow_forward:")
with how_it_works("The control loop as a diagram"):
    diagram("""
flowchart LR
    S["① Sensors<br/>12 rack inlets, power,<br/>weather · every 15 min"]:::step --> CL["② Clean<br/>gaps, glitches,<br/>stuck sensors"]:::step
    CL --> F["③ Forecast (ML)<br/>next 60 min for<br/>any setpoint plan"]:::ai
    F --> M["④ MPC<br/>try 81 plans → keep safe<br/>→ pick cheapest"]:::ai
    M --> SF["⑤ Safety filter<br/>6 rules check<br/>every command"]:::guard
    SF --> P["⑥ Room<br/>apply the setpoint,<br/>repeat in 15 min ↺"]:::ok
""", alt="Control loop: sensors, clean, forecast, MPC, safety filter, room, then repeat every 15 minutes")

st.subheader("Five agents, four guards", icon=":material/groups:")
st.caption("An operator asks a question about one moment; the agents answer it with checked tools, never with numbers of "
           "their own.")
agents = [
    (":material/supervisor_account:", "Supervisor", "Plans the case, delegates, writes the verified answer."),
    (":material/query_stats:", "Data Analyst", "Reads the sensors, checks their quality, forecasts the next hour."),
    (":material/security:", "Security Analyst", "Are the readings genuine? Forged, replayed or written by someone else?"),
    (":material/memory:", "Hardware Engineer", "Polls 22 devices, finds faults days early, plans upgrades."),
    (":material/ac_unit:", "Cooling Advisor", "Runs the 81-plan MPC and the safety filter, proposes a setpoint."),
]
for col, (icon, name, body) in zip(st.columns(5), agents):
    with col.container(border=True, height="stretch"):
        st.markdown(f"{icon} **{name}**")
        st.caption(body)
st.markdown(":red-badge[G1 · checks the request and screens the question] :red-badge[G2 · allows only each skill's tools] "
            ":red-badge[G3 · recomputes everything, rejects a mismatch] :red-badge[G4 · redacts, signs, seals the trace]")
with how_it_works("The agent layer as a diagram"):
    diagram("""
flowchart LR
    Q(["Operator question"]):::step --> G1["G1 check request<br/>+ prompt screen"]:::guard
    G1 --> SUP["Supervisor<br/>plans the case"]:::agent
    SUP --> DA["Data Analyst<br/>reads sensors + forecast"]:::agent
    DA --> SA["Security Analyst<br/>forged? replayed?<br/>unauthorised writes?"]:::agent
    SA --> HE["Hardware Engineer<br/>polls 22 devices,<br/>limits · trends · N+1"]:::agent
    HE --> CA["Cooling Advisor<br/>81-plan MPC + safety"]:::agent
    CA --> G3["G3 recompute<br/>everything, reject<br/>if it does not match"]:::guard
    G3 --> G4["G4 screen notes,<br/>sign, audit chain"]:::guard
    G4 --> A(["Verified answer"]):::ok
""", alt="Agent layer: operator question, G1, Supervisor, Data Analyst, Security Analyst, Hardware Engineer, Cooling Advisor, G3, G4, verified answer")
    st.caption("Every tool call passes guard G2: allowed tools for that skill, a shared budget, and no peeking past the chosen time.")

st.subheader("Beyond the setpoint", icon=":material/explore:")
for col, (page, icon, head, body) in zip(st.columns(3), [
    ("app_pages/hardware.py", ":material/memory:", "Equipment health",
     "A clogging filter, a worn pump bearing and a fouled condenser show up in the equipment data **days before** any rack "
     "gets hot."),
    ("app_pages/security.py", ":material/security:", "Security",
     f"When an attacker forges the GPU racks' readings, the AI without the integrity check overheats them for **{blind:.0f} "
     f"minutes**; with it, **{guarded:.0f}**."),
    ("app_pages/upgrades.py", ":material/construction:", "Upgrade advisor",
     f"Every upgrade tested in closed loop with the AI: all of them together save **{package['saved_facility_pct']:.1f} %** of "
     f"the facility's energy, ≈ {package['saved_tco2_yr']:g} tCO₂ a year."),
]):
    with col.container(border=True, height="stretch"):
        st.markdown(f"{icon} **{head}**")
        st.markdown(body)
        st.page_link(page, label="Open", icon=":material/arrow_forward:")
