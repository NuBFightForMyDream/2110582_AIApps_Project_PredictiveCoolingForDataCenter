"""Overview: what the project does, its results, and where to go next."""
import streamlit as st

from predictive_cooling.hardware import advisor as hw_advisor
from ui.common import B, HEAD, diagram, kpi, kpi_row, signed

ai = HEAD["ai"]
summary = B["summary"].set_index(["scenario", "key"])
blind = summary.loc[("spoofing_attack", "ai_no_integrity"), "violation_minutes"]
guarded = summary.loc[("spoofing_attack", "ai"), "violation_minutes"]
package = next(o for o in hw_advisor.plan(B["upgrades"])["options"] if o["key"] == "package")

left, right = st.columns([1.2, 1], gap="large", vertical_alignment="center")
with left:
    st.title("Predictive cooling for a data center", icon=":material/ac_unit:")
    st.markdown("Server rooms are cooled colder than they need. This project **forecasts the next hour** and picks the "
                "warmest cooling setpoint that keeps every rack at or below **27 °C**, with AI agents that check the data "
                "and the equipment first.")
    with st.container(horizontal=True):
        st.page_link("app_pages/agents.py", label="Ask the agents", icon=":material/smart_toy:")
        st.page_link("app_pages/how_it_works.py", label="How it works", icon=":material/account_tree:")
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
            help="Every hardware option together, with the AI, measured in closed loop (Upgrades page)"))

diagram("""
flowchart LR
    S["Sensors<br/>every 15 min"]:::step --> F["Forecast<br/>next hour (ML)"]:::ai --> M["Try 81 plans<br/>keep safe, pick cheapest"]:::ai
    M --> SF["Safety rules"]:::guard --> P["Room"]:::ok
""", alt="Every 15 minutes: sensors, forecast, 81 plans, safety rules, room")

st.subheader("Explore", icon=":material/explore:")
for col, (page, icon, head, body) in zip(st.columns(4), [
    ("app_pages/results.py", ":material/bolt:", "Results", "Energy saved and overheating, three controllers, fault tests."),
    ("app_pages/data_center.py", ":material/factory:", "Data center", "The live plant, its flows and the health of 22 devices."),
    ("app_pages/security.py", ":material/security:", "Security", "Forged and replayed sensor data, caught by an ML check."),
    ("app_pages/upgrades.py", ":material/construction:", "Upgrades", "Which hardware upgrade pays back, with the AI on top."),
]):
    with col.container(border=True, height="stretch"):
        st.markdown(f"{icon} **{head}**")
        st.caption(body)
        st.page_link(page, label="Open", icon=":material/arrow_forward:")
st.caption("All data is a mock 12-rack room from a physics model. Nothing here controls real equipment.")
