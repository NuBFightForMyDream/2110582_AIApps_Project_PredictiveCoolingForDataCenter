"""Shared look & feel, data and layout helpers for every dashboard page.

Pages import what they need from here. Data loads once per process (st.cache_resource); each page computes only
what it shows, so switching pages is fast.
"""
import sys

import pandas as pd
import streamlit as st

from predictive_cooling import config as C
from predictive_cooling import pipeline
from predictive_cooling.evaluate import scenarios, security_scenarios
from predictive_cooling.hardware import telemetry as hw_telemetry
from predictive_cooling.hardware.diagnostics import EquipmentWindow, diagnose

from .art import ART

# ---------- palette -------------------------------------------------------------------------
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
CTRL = {"fixed": "#1baf7a", "rule": "#eb6834", "ai": "#2a78d6", "ai_unsafe": "#eda100", "ai_no_integrity": "#6250d6"}
MODEL = {"persistence": MUTED, "linear": "#eb6834", "gbm": "#2a78d6"}
QTY = {"temp": "#6250d6", "it": "#e87ba4", "cooling": "#eda100"}
LIMIT = "#d03b3b"
WARN, CRIT = "#eb6834", LIMIT
FONT = "system-ui, -apple-system, Segoe UI, sans-serif"

# Mermaid class styles shared by every diagram: blue = ML/AI step, red = guard/safety, green = outcome, violet = agent.
MERMAID_STYLE = """
    classDef step fill:#ffffff,stroke:#c3c2b7,color:#0b0b0b
    classDef ai fill:#e8f1fc,stroke:#2a78d6,color:#0b0b0b,stroke-width:2px
    classDef guard fill:#fbeeee,stroke:#d03b3b,color:#0b0b0b
    classDef ok fill:#e6f6ef,stroke:#1baf7a,color:#0b0b0b
    classDef agent fill:#f1effc,stroke:#6250d6,color:#0b0b0b
"""


def diagram(body, alt):
    """A Mermaid diagram; flowcharts get the shared colour classes (other diagram types reject classDef)."""
    body = body.strip()
    st.mermaid_chart(body + "\n" + MERMAID_STYLE if body.startswith("flowchart") else body, alt=alt)


def page_header(title, icon, lead, art=None):
    """Title and one plain sentence on the left, the page's small illustration on the right."""
    left, right = st.columns([4.2, 1], vertical_alignment="center", gap="large")
    with left:
        st.title(title, icon=icon)
        st.markdown(lead)
    if art:
        right.image(ART[art], width="stretch", alt=f"Illustration: {title}")


def how_it_works(label="How it works", expanded=False, icon=":material/account_tree:"):
    """The collapsible place for diagrams, method notes and secondary charts, so each page stays short."""
    return st.expander(label, expanded=expanded, icon=icon)


def style(fig, height=320, title=None, legend=True, hover="x unified"):
    subtitles = [a for a in fig.layout.annotations if a.xref == "paper" and a.yref == "paper" and a.yanchor == "bottom"]
    for a in subtitles:
        a.update(font=dict(size=13, color=INK2))
    top = (46 if title else 12) + (22 if subtitles and not title else 0) + (26 if legend and title and not subtitles else 0)
    bottom_legend = bool(subtitles) and legend
    fig.update_layout(
        height=height, title=dict(text=title, font=dict(size=15, color=INK), y=0.98, yanchor="top") if title else None,
        margin=dict(l=8, r=8, t=top, b=64 if bottom_legend else 8), plot_bgcolor=SURFACE, paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=INK2, size=12.5), hovermode=hover, showlegend=legend, barcornerradius=4,
        legend=dict(orientation="h", yanchor="top" if bottom_legend else "bottom", y=-0.11 if bottom_legend else 1.02, x=0,
                    title=None, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(font=dict(family=FONT)),
    )
    fig.update_xaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False, showline=True)
    fig.update_yaxes(gridcolor=GRID, linecolor=AXIS, zeroline=False)
    return fig


def show(fig):
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def limit_line(fig, row=None, col=None, label="27 °C limit"):
    kw = dict(row=row, col=col) if row else {}
    fig.add_hline(y=C.INLET_LIMIT, line=dict(color=LIMIT, width=1.5), annotation_text=label,
                  annotation_position="top left", annotation_font=dict(color=LIMIT, size=11), **kw)


def hw_limit(fig, y, row, col, text, color):
    fig.add_hline(y=y, line=dict(color=color, width=1.2, dash="dot"), annotation_text=text, annotation_position="top left",
                  annotation_font=dict(color=color, size=10.5), row=row, col=col)


def kpi(label, value, note=None, help=None, icon=None):
    """One metric card for kpi_row(); `note` is a small grey line, not an up/down change."""
    return dict(label=label, value=str(value), note=note, help=help, icon=icon)


def _needed_width(k):
    """Pixels a card needs so nothing is cut off (generous per-character widths for the theme's Inter font)."""
    value = 23 * len(k["value"]) + 44
    label = 8.6 * len(k["label"]) + 44 + (24 if k["help"] else 0) + (28 if k["icon"] else 0)
    note = 8.6 * len(k["note"]) + 64 if k["note"] else 0
    return int(max(value, label, note, 150))


def kpi_row(*items, max_width=320, uniform=True):
    """Metric cards in a row that wraps onto the next line when the page gets narrow (e.g. the sidebar opens),
    instead of cutting values to "1,151 …". Cards share one width, wide enough for the longest of them; a card that
    needs more than `max_width` (a long answer) gets its own width and does not widen the others. Use it at full page
    width: inside a narrow column the cards would simply stack. `uniform=False` sizes every card to its own content."""
    needs = [_needed_width(k) for k in items]
    shared = max([n for n in needs if n <= max_width] or [max_width]) if uniform else 0
    with st.container(horizontal=True, gap="small"):
        for k, need in zip(items, needs):
            st.metric(k["label"], k["value"], k["note"], delta_color="off", delta_arrow="off", help=k["help"], icon=k["icon"],
                      border=True, width=max(shared, need), height="stretch")


def signed(x, digits=1):
    return f"{x:+.{digits}f} %".replace("-", "−")


# ---------- data ----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def get_bundle():
    bundle = pipeline.load(rebuild_if_stale=False)
    if bundle is None:
        with st.status("First run: generating data, training models and running the plant tests (2–5 min)…",
                       expanded=True) as status:
            bundle = pipeline.build(workers=4 if sys.platform == "linux" else 1, log=st.write)
            status.update(label="Ready", state="complete")
    return bundle


@st.cache_resource(show_spinner=False)
def get_equipment():
    """The equipment historian (data/equipment_telemetry.csv); built from the plant run in ~1 s if missing."""
    return hw_telemetry.load()


B = get_bundle()
EQUIP = get_equipment()
SC = scenarios()
SEC = security_scenarios()
NAMES = B["controller_names"]
LOGS = B["logs"]
CLEAN, RAW = B["clean"], B["raw"]
TEST_DAYS = sorted({d for d in LOGS["normal", "ai"].index.date})
HEAD = pipeline.headline(B)
TIMES = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 15, 30, 45)]


@st.cache_data(max_entries=48, show_spinner=False)
def hardware_state(at: str, trips: tuple = ()):
    """Gateway poll + diagnosis at one moment (what the Hardware Engineer would see)."""
    win = EquipmentWindow(EQUIP, pd.Timestamp(at), trips=trips)
    return win.snapshot, diagnose(win)


# ---------- the moment every page looks at --------------------------------------------------------
JUMPS = {
    "GPU batch about to start": ("2026-04-21", "00:30"),
    "During the GPU batch": ("2026-04-21", "02:00"),
    "Cooling tower offline": ("2026-04-26", "15:00"),
    "Hardware warnings": ("2026-04-29", "05:30"),
    "Pump bearing critical": ("2026-05-02", "12:00"),
}


def _jump():
    pick = st.session_state.get("moment_jump")
    if pick:
        day, clock = JUMPS[pick]
        st.session_state.moment_day, st.session_state.moment_time = pd.Timestamp(day).date(), clock


def moment_picker():
    """Sidebar controls shared by every page: one moment in the two test weeks, plus shortcuts to telling ones."""
    st.markdown(":material/schedule: **Moment**")
    st.selectbox("Day", TEST_DAYS, index=1, format_func=lambda d: f"{pd.Timestamp(d):%a %d %b}", key="moment_day")
    st.select_slider("Time", options=TIMES, value="00:30", key="moment_time")
    st.pills("Jump to", list(JUMPS), key="moment_jump", on_change=_jump)
    st.caption("The two test weeks (20 Apr – 3 May 2026) the AI never trained on. Every page follows this moment.")


def moment() -> pd.Timestamp:
    day = st.session_state.get("moment_day", TEST_DAYS[1])
    return pd.Timestamp(f"{day} {st.session_state.get('moment_time', '00:30')}")

