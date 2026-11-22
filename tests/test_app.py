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


def test_every_metric_card_has_a_width_that_fits_its_text(monkeypatch):
    """Metrics must go through ui.common.kpi_row: a fixed width computed from their text inside a wrapping row.
    A metric stretched across a narrow column cuts its value ("1,151 …") when the sidebar opens."""
    import streamlit as st
    from ui.common import _needed_width, kpi
    widths = []
    original = st.metric                         # bound to the main container when Streamlit is imported

    def recording(label, value, delta=None, *args, **kwargs):
        widths.append((label, str(value), delta, kwargs.get("help"), kwargs.get("icon"), kwargs.get("width")))
        return original(label, value, delta, *args, **kwargs)
    monkeypatch.setattr(st, "metric", recording)
    for page in PAGES:
        render(page)
    assert widths
    pages = sorted((Path(APP).parent / "app_pages").glob("*.py"))
    assert not [f.name for f in pages if ".metric(" in f.read_text()], "pages must use ui.common.kpi_row, not .metric()"
    for label, value, note, help_, icon, width in widths:
        assert isinstance(width, int), f"{label!r} is not in a kpi_row"
        assert width >= _needed_width(kpi(label, value, note, help_, icon)), f"{label!r} = {value!r} is too narrow"
