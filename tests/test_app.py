"""Dashboard smoke tests: the whole app renders without an exception (headless, no browser, offline agent mode).

Widget values are preset through session_state and each scenario is one fresh run: on its first render the
agents tab runs a case with the current inputs, so this exercises the full agent + hardware path.
"""
import datetime as dt
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def render(**preset):
    at = AppTest.from_file(APP, default_timeout=300)
    for key, value in preset.items():
        at.session_state[key] = value
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at, {m.label: m.value for m in at.metric}


def test_app_renders_every_tab():
    at, metrics = render()
    assert [t.label.split(" ", 1)[1] for t in at.tabs] == ["Ask the agents", "1 · Sensors", "2 · Clean data", "3 · Forecast",
                                                          "4 · MPC decision", "5 · Safety", "6 · Results", "Hardware"]
    assert metrics["Agents' answer"] == "Set 21 °C" and metrics["Status"] == "completed"
    assert metrics["Devices answering"] == "22 / 22"


@pytest.mark.parametrize("preset, constraint", [
    ({"hw_trips": ["CRAH-1"]}, "fallback"),
    ({"hw_day": dt.date(2026, 4, 26), "hw_time": "15:00"}, "no raise"),        # cooling tower not answering
    ({"hw_day": dt.date(2026, 4, 21), "hw_time": "00:30"}, "none"),            # before the faults start
])
def test_hardware_tab_follows_the_moment_and_trips(preset, constraint):
    _, metrics = render(**preset)
    assert metrics["Cooling constraint"] == constraint
