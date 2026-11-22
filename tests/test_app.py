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
PAGES = {"home": "Predictive cooling for a data center", "agents": "Ask the agents", "results": "Results",
         "data_center": "Data center", "security": "Security", "upgrades": "Upgrades", "how_it_works": "How it works"}
STEPS = ["1 · Sensors", "2 · Clean", "3 · Forecast", "4 · Plan", "5 · Safety"]


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
    _, metrics = render("data_center", **preset)
    assert metrics["Cooling constraint"] == constraint


def test_data_center_handles_a_device_that_does_not_answer():
    _, metrics = render("data_center", moment_day=dt.date(2026, 4, 26), moment_time="15:00")
    assert metrics["PUE"].startswith("1.") and metrics["Equipment health"] == "Warning"


@pytest.mark.parametrize("step", STEPS)
def test_every_how_it_works_step_renders(step):
    at, _ = render("how_it_works", how_step=step)
    assert at.title[0].value == "How it works"


@pytest.mark.parametrize("scenario", ["normal", "sensor_failure", "plant_change", "load_surge"])
def test_results_shows_every_scenario(scenario):
    render("results", res_sc=scenario)


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
    for step in STEPS:
        render("how_it_works", how_step=step)
    assert widths
    pages = sorted((Path(APP).parent / "app_pages").glob("*.py"))
    assert not [f.name for f in pages if ".metric(" in f.read_text()], "pages must use ui.common.kpi_row, not .metric()"
    for label, value, note, help_, icon, width in widths:
        assert isinstance(width, int), f"{label!r} is not in a kpi_row"
        assert width >= _needed_width(kpi(label, value, note, help_, icon)), f"{label!r} = {value!r} is too narrow"
