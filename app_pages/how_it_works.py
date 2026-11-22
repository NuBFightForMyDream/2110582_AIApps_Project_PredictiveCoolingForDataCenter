"""How it works: the 15-minute loop, one step at a time (only the chosen step is computed)."""
import streamlit as st

from ui.common import diagram, page_header
from ui.steps import STEPS

page_header("How it works", ":material/account_tree:", "Every 15 minutes the same steps run, then the room is checked again. "
            "Pick a step; it follows the moment in the sidebar.", art="forecast")
diagram("""
flowchart LR
    S["1 · Sensors"]:::step --> CL["2 · Clean"]:::step --> F["3 · Forecast (ML)"]:::ai --> M["4 · Plan: 81 options"]:::ai
    M --> SF["5 · Safety rules"]:::guard --> P["Room ↺ 15 min"]:::ok
""", alt="The loop: sensors, clean, forecast, plan, safety rules, room, every 15 minutes")
step = st.segmented_control("Step", list(STEPS), default=list(STEPS)[0], key="how_step") or list(STEPS)[0]
STEPS[step]()
