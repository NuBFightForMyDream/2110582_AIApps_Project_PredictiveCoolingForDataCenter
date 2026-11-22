"""Predictive Cooling dashboard: a multipage Streamlit app.

    streamlit run app.py          (or: python -m predictive_cooling)

This file is the frame around every page: page setup, secrets, the shared moment picker and the navigation.
Each page lives in app_pages/; shared helpers, data and illustrations live in ui/.
"""
import os

# One thread per math library, set before numpy / scikit-learn load. Otherwise OpenMP/BLAS start one thread per
# host core; on Streamlit Cloud (many host cores, ~1 core of quota) that oversubscription used ~10x more CPU per
# rerun and got the app throttled. Measured locally: 3.5 s → 0.3 s CPU per rerun, and faster wall time.
for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import streamlit as st  # noqa: E402
from threadpoolctl import threadpool_limits  # noqa: E402

# The env vars above only help if numpy/sklearn were not loaded yet, and Streamlit runs every rerun in a new thread
# (OpenMP thread counts are per thread), so also cap the already-loaded pools on every run.
threadpool_limits(limits=1)

st.set_page_config(page_title="Predictive Cooling", page_icon=":material/ac_unit:", layout="wide")

# Deployed keys live in Streamlit secrets (.streamlit/secrets.toml locally, the Secrets box on Streamlit Cloud).
# The agent and storage code read environment variables, so copy the known keys across once.
for _name in ("GEMINI_API_KEY", "GEMINI_MODEL", "ANTHROPIC_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", "COMMAND_SIGNING_KEY"):
    try:
        if not os.getenv(_name) and _name in st.secrets:
            os.environ[_name] = str(st.secrets[_name])
    except Exception:                                   # no secrets file: environment variables only
        break

from ui.art import LOGO  # noqa: E402
from ui.common import moment_picker  # noqa: E402   (loads the study once per process)

st.logo(LOGO, size="large")
page = st.navigation({
    "": [
        st.Page("app_pages/home.py", title="Overview", icon=":material/home:", default=True),
        st.Page("app_pages/agents.py", title="Ask the agents", icon=":material/smart_toy:"),
    ],
    "Operations": [
        st.Page("app_pages/live_plant.py", title="Live plant", icon=":material/factory:"),
        st.Page("app_pages/hardware.py", title="Equipment health", icon=":material/memory:"),
        st.Page("app_pages/upgrades.py", title="Upgrade advisor", icon=":material/construction:"),
        st.Page("app_pages/security.py", title="Security", icon=":material/security:"),
    ],
    "How the AI decides": [
        st.Page("app_pages/sensors.py", title="1 · Sensors", icon=":material/sensors:"),
        st.Page("app_pages/cleaning.py", title="2 · Clean data", icon=":material/cleaning_services:"),
        st.Page("app_pages/forecast.py", title="3 · Forecast", icon=":material/insights:"),
        st.Page("app_pages/mpc.py", title="4 · Plan (MPC)", icon=":material/route:"),
        st.Page("app_pages/safety.py", title="5 · Safety", icon=":material/shield:"),
        st.Page("app_pages/results.py", title="6 · Results", icon=":material/bolt:"),
    ],
}, position="top")

with st.sidebar:
    moment_picker()

page.run()

st.caption("Mock data from a simplified physics model (predictive_cooling/plant.py). Results show the method, not the savings of "
           "a real facility. The tool recommends; it never controls equipment.")
