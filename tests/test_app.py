"""Dashboard smoke tests: every page renders without an exception (headless, no browser, offline agent mode).

Widget values are preset through session_state and each scenario is one fresh run. The sidebar's moment picker
(moment_day / moment_time) drives every page. On its first render the agents page runs a case with the current
inputs, so this exercises the full agent + hardware + security path.
"""
import datetime as dt
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
PAGES = {"home": "Predictive cooling for a data center", "agents": "Ask the agents", "live_plant": "Live plant",
         "hardware": "Equipment health", "upgrades": "Upgrade advisor", "security": "Security", "sensors": "Sensors",
         "cleaning": "Clean data", "forecast": "Forecast", "mpc": "Plan (MPC)", "safety": "Safety", "results": "Results"}


def render(page="home", **preset):
    at = AppTest.from_file(APP, default_timeout=300)
    for key, value in preset.items():
        at.session_state[key] = value
    at.run()
    if page != "home":
        at.switch_page(f"app_pages/{page}.py").run()
    assert not at.exception, [e.value for e in at.exception]
    return at, {m.label: m.value for m in at.metric}


@pytest.mark.parametrize("page", list(PAGES))
def test_every_page_renders(page):
    at, _ = render(page)
    assert at.title[0].value == PAGES[page]


def test_agents_page_answers_the_default_case():
    _, metrics = render("agents")
    assert metrics["Agents' answer"] == "Set 21 °C" and metrics["Status"] == "completed"


@pytest.mark.parametrize("preset, constraint", [
    ({"hw_trips": ["CRAH-1"]}, "fallback"),
    ({"moment_day": dt.date(2026, 4, 26), "moment_time": "15:00"}, "no raise"),       # cooling tower not answering
    ({"moment_day": dt.date(2026, 4, 29), "moment_time": "05:30"}, "no raise"),       # filter, bearing, N+1 lost
    ({"moment_day": dt.date(2026, 4, 21), "moment_time": "00:30"}, "none"),           # before the faults start
])
def test_equipment_health_follows_the_sidebar_moment(preset, constraint):
    _, metrics = render("hardware", **preset)
    assert metrics["Cooling constraint"] == constraint


def test_live_plant_handles_a_device_that_does_not_answer():
    _, metrics = render("live_plant", moment_day=dt.date(2026, 4, 26), moment_time="15:00")
    assert metrics["PUE"].startswith("1.")
