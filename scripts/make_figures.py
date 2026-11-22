"""Regenerate the README figures in docs/ from the study (matplotlib, no browser needed).

    .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/python scripts/make_figures.py

architecture.png    the whole system on one picture (agents, guards, tools, layers)
agents-trace.png    who did what in a real offline case (21 Apr 00:30)
hardware-trends.png the four hidden equipment faults with their limits
attacks.png         the sensor-spoofing attack in closed loop, with and without the integrity check
upgrades.png        each hardware upgrade, alone and with the AI
"""
from pathlib import Path
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from predictive_cooling import config as C, pipeline  # noqa: E402
from predictive_cooling.agents import AgentContext, CaseRequest, run_case  # noqa: E402
from predictive_cooling.agents.skills import ROLES  # noqa: E402
from predictive_cooling.hardware import advisor, telemetry  # noqa: E402
from predictive_cooling.hardware.diagnostics import RULES, metrics  # noqa: E402
from predictive_cooling.hardware.registry import REGISTRY  # noqa: E402
from predictive_cooling.security.integrity import REPEAT_LIMIT_C, SINGLE_LIMIT_C  # noqa: E402

DOCS = ROOT / "docs"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
BLUE, ORANGE, GREEN, VIOLET, RED, YELLOW, PINK = "#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#d03b3b", "#eda100", "#e87ba4"
CTRL = {"fixed": GREEN, "rule": ORANGE, "ai": BLUE, "ai_no_integrity": VIOLET}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
                     "axes.facecolor": SURFACE, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 11.5, "axes.titlecolor": INK, "legend.frameon": False})


def card(ax, x, y, w, h, title, body, fill="#ffffff", edge=AXIS, width=26):
    """A rounded card: bold title (a "\n" splits name and tag), then the wrapped body below it."""
    name, _, tag = title.partition("\n")
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.6", fc=fill, ec=edge, lw=1.4))
    ax.text(x + 1.4, y + h - 2.2, name, fontsize=10.5, fontweight="bold", color=INK, va="top")
    top = y + h - 6.0
    if tag:
        ax.text(x + 1.4, top, tag, fontsize=9, fontweight="bold", color={"#b7aef0": VIOLET, "#eba7a7": RED}.get(edge, MUTED),
                va="top")
        top -= 3.6
    ax.text(x + 1.4, top, textwrap.fill(body, width), fontsize=9, color=INK2, va="top", linespacing=1.35)


def arrow(ax, x0, y, x1):
    ax.annotate("", xy=(x1, y), xytext=(x0, y), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.2))


def architecture():
    fig, ax = plt.subplots(figsize=(17, 7.6))
    ax.set_xlim(0, 170), ax.set_ylim(0, 77), ax.axis("off")
    agent, guard, ml, ok, plain = ("#f1effc", "#b7aef0"), ("#fbeeee", "#eba7a7"), ("#e8f1fc", "#86b6ef"), ("#e6f6ef", "#8fd8b8"), ("#ffffff", AXIS)
    rows = [
        (74.5, "AGENT LAYER · LANGGRAPH · OFFLINE ROLES, OR GEMINI / CLAUDE FUNCTION CALLING", 52, [
            ("Request\nG1", "typed request, case time, budgets, prompt-injection screen", guard),
            ("Supervisor\nS1", "plans the case, delegates in order", agent),
            ("Data Analyst\nS2 · S3", "inspects sensors, state, forecast", agent),
            ("Security Analyst\nS7", "forged? replayed? unauthorised writes?", agent),
            ("Hardware Eng.\nS6 · S8", "22 devices, limits, trends, N+1, upgrades", agent),
            ("Cooling Advisor\nS4", "81-plan MPC + safety → proposal", agent),
            ("Verify\nG3", "re-read, re-poll, recompute, reject mismatch", guard),
            ("Release\nS5 · G4", "verified answer, notes redacted, signed, hash-chained", guard)]),
        (47.5, "TOOLS THE AGENTS CALL (EVERY CALL PASSES G2) · THE SAME STEPS RUN THE 15-MINUTE CONTROL LOOP", 25, [
            ("① Sensors", "12 rack inlets, power, CRAH, weather · every 15 min", plain),
            ("② Clean", "gaps, glitches, stuck sensors, short fills", plain),
            ("③ Forecast (ML)", "next 15–60 min for any setpoint plan", ml),
            ("④ MPC", "81 plans → safe → cheapest → apply first step", ml),
            ("⑤ Safety R1–R6", "missing, unfamiliar, too hot, rate, hardware, untrusted", guard),
            ("⑥ Plant & results", "simulated room is the judge vs 2 baselines", ok)]),
        (19, "LAYERS AROUND THE LOOP", 0, [
            ("Hardware layer", "BACnet / Modbus / SNMP gateway, equipment historian, diagnostics → R5", plain),
            ("Security layer", "integrity model (inlet vs PDU power), replay, command audit → R6; G1/G4", guard),
            ("Upgrade study", "6 options on the upgraded plant: hardware alone vs with the AI", ok),
            ("Dashboard", "12 pages, one sidebar moment, Streamlit", plain)]),
    ]
    for top, label, base, cards in rows:
        ax.text(0.5, top, label, fontsize=9.5, color=MUTED, fontweight="bold", va="center")
        n = len(cards)
        gap = 2.4
        w = (170 - 1 - gap * (n - 1)) / n
        for i, (title, body, (fill, edge)) in enumerate(cards):
            x = 0.5 + i * (w + gap)
            card(ax, x, base + 1, w, 19 if top > 20 else 15, title, body, fill, edge, width=int(w * 1.15))
            if i and top > 20:
                arrow(ax, x - gap + 0.2, base + 10, x - 0.2)
    fig.savefig(DOCS / "architecture.png", dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def agents_trace(ctx):
    result = run_case(CaseRequest(at="2026-04-21 00:30"), ctx)
    lanes = ["G1", "supervisor", "G2", "data_analyst", "security_analyst", "hardware_engineer", "cooling_advisor", "G3", "G4"]
    names = {"G1": "G1 request", "G2": "G2 gateway", "G3": "G3 verify", "G4": "G4 release", **ROLES}
    colors = {"passed": GREEN, "completed": BLUE, "authorized": "#86b6ef", "blocked": RED, "rejected": RED, "failed": RED}
    ev = pd.DataFrame([e.model_dump() for e in result.events])
    ev = ev[ev["actor"].isin(lanes)]
    y = ev["actor"].map({a: len(lanes) - i for i, a in enumerate(lanes)})
    fig, ax = plt.subplots(figsize=(15, 5))
    ax.plot(ev["step"], y, color=GRID, lw=1, zorder=1)
    for status, color in colors.items():
        part = ev["status"] == status
        if part.any():
            ax.scatter(ev["step"][part], y[part], s=70, color=color, edgecolor="white", lw=1.5, zorder=3, label=status)
    ax.set_yticks(range(1, len(lanes) + 1), [names[a] for a in reversed(lanes)])
    ax.set_xlabel("step")
    ax.legend(ncol=6, loc="upper center", bbox_to_anchor=(0.5, 1.13))
    ax.set_title(f"Who did what in one offline case (21 Apr 00:30): {len(result.events)} events, {result.tool_calls} tool calls, "
                 f"G3 {sum(c.passed for c in result.checks)}/{len(result.checks)} checks, answer {result.recommended_setpoint:g} °C",
                 loc="left", pad=34)
    fig.savefig(DOCS / "agents-trace.png", dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def hardware_trends(equipment):
    frame = equipment.loc["2026-04-06":]
    pdu = equipment[[REGISTRY[f"PDU-{r}"].column("power_kw") for r in C.RACKS]].sum(axis=1).rolling("7D").max().loc["2026-04-06":]
    hourly = lambda s: s.resample("1h").mean()  # noqa: E731
    limits = {r.code: (r.warning, r.critical) for r in RULES}
    fig, axes = plt.subplots(2, 3, figsize=(16, 7.2), sharex=True)
    spec = [
        ("CRAH filter ΔP at 100 % fan (Pa)", [("CRAH-1", hourly(metrics(frame, REGISTRY["CRAH-1"])["filter_dp_100_pa"]), MUTED),
                                               ("CRAH-2", hourly(metrics(frame, REGISTRY["CRAH-2"])["filter_dp_100_pa"]), BLUE)],
         [(limits["FILTER_LOADING"][0], "warning", ORANGE)]),
        ("CHWP-1 vibration (mm/s RMS, ISO 10816)", [("CHWP-1", hourly(frame["CHWP-1.vibration_mm_s"]), BLUE)],
         [(1.8, "zone C", ORANGE), (4.5, "zone D", RED)]),
        ("CH-1 condenser approach (°C)", [("CH-1", hourly(frame["CH-1.cond_approach_c"]), BLUE)],
         [(3.0, "warning", ORANGE), (5.0, "critical", RED)]),
        ("Humidity sensor vs CRAH reference (|Δ| %RH)", [
            ("ENV-CA-1", hourly(metrics(frame, REGISTRY["ENV-CA-1"])["rh_deviation_pct"]), MUTED),
            ("ENV-CA-2", hourly(metrics(frame, REGISTRY["ENV-CA-2"])["rh_deviation_pct"]), VIOLET)], [(5.0, "warning", ORANGE)]),
        ("N+1: CRAH-2 capacity vs week-peak IT (kW)", [
            ("CRAH-2 capacity", hourly(140 * (frame["CRAH-2.airflow_m3h"] / (34000 * frame["CRAH-2.fan_speed_pct"] / 100)).clip(.5, 1)), BLUE),
            ("week-peak IT load", hourly(pdu), PINK)], []),
        ("Cold-aisle over-pressure (Pa)", [("ENV-DP-1", hourly(frame["ENV-DP-1.aisle_dp_pa"]), BLUE)], [(1.0, "warning", ORANGE)]),
    ]
    for ax, (title, series, lines) in zip(axes.flat, spec):
        for label, s, color in series:
            ax.plot(s.index, s.values, color=color, lw=1.6, label=label)
        for y, text, color in lines:
            ax.axhline(y, color=color, ls=":", lw=1.3)
            ax.text(s.index[0], y, f" {text} {y:g}", color=color, fontsize=8.5, va="bottom")
        ax.axvspan(pd.Timestamp(C.VAL_END), s.index[-1], color="#f0efec", zorder=0)
        ax.set_title(title, loc="left")
        if len(series) > 1:
            ax.legend(fontsize=8.5, loc="lower left" if title.startswith("N+1") else "upper left")
        ax.xaxis.set_major_locator(mdates.DayLocator(bymonthday=(6, 13, 20, 27)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.suptitle("Four faults hidden in the equipment data, seen days before any rack gets hot (grey = the two test weeks)",
                 x=0.01, ha="left", fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(DOCS / "hardware-trends.png", dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def attacks(bundle):
    logs, names = bundle["logs"], bundle["controller_names"]
    lo, hi = pd.Timestamp("2026-04-20 21:30"), pd.Timestamp("2026-04-21 08:30")
    fig, axes = plt.subplots(3, 1, figsize=(14, 8.4), sharex=True, gridspec_kw=dict(height_ratios=[1.4, 1, 1]))
    for key in ["fixed", "rule", "ai_no_integrity", "ai"]:
        part = logs["spoofing_attack", key].loc[lo:hi]
        axes[0].plot(part.index, part["max_inlet_c"], color=CTRL[key], lw=2, label=names[key])
        axes[1].step(part.index, part["command"], where="post", color=CTRL[key], lw=2)
    part = logs["spoofing_attack", "ai"].loc[lo:hi]
    axes[2].plot(part.index, part["min_residual_c"], color=INK2, lw=1.8, label="worst rack: reported − expected")
    axes[2].axhline(SINGLE_LIMIT_C, color=RED, ls=":", lw=1.3)
    axes[2].axhline(REPEAT_LIMIT_C, color=ORANGE, ls=":", lw=1.3)
    axes[0].axhline(C.INLET_LIMIT, color=RED, lw=1.4)
    axes[0].text(lo, C.INLET_LIMIT + 0.1, " 27 °C limit", color=RED, fontsize=9)
    for ax in axes:
        ax.axvspan(pd.Timestamp("2026-04-21 00:30"), pd.Timestamp("2026-04-21 05:30"), color="#fbeeee", zorder=0)
    summary = bundle["summary"].set_index(["scenario", "key"])
    minutes = {k: summary.loc[("spoofing_attack", k), "violation_minutes"] for k in ("rule", "ai_no_integrity", "ai")}
    fig.suptitle(f"Sensor spoofing: B4–B6 read 2.5 °C cooler during the GPU batch (pink band).\nMinutes above 27 °C over "
                 f"the 14 test days: rule-based {minutes['rule']}, AI without the integrity check {minutes['ai_no_integrity']}, "
                 f"AI with it {minutes['ai']}", x=0.01, ha="left", fontweight="bold", color=INK)
    axes[0].set_ylabel("true hottest inlet (°C)"), axes[1].set_ylabel("setpoint sent (°C)"), axes[2].set_ylabel("integrity residual (°C)")
    axes[0].legend(ncol=4, loc="lower left", bbox_to_anchor=(0, 1.0)), axes[2].legend(loc="lower left")
    axes[2].xaxis.set_major_formatter(mdates.DateFormatter("%a %H:%M"))
    fig.tight_layout()
    fig.savefig(DOCS / "attacks.png", dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def upgrades(bundle):
    opts = sorted(advisor.plan(bundle["upgrades"])["options"], key=lambda o: o["saved_facility_pct"])
    fig, ax = plt.subplots(figsize=(13, 5))
    y = range(len(opts))
    ax.barh([i + 0.2 for i in y], [o["hardware_only_facility_pct"] for o in opts], height=0.38, color=ORANGE,
            label="hardware + rule-based controller")
    ax.barh([i - 0.2 for i in y], [o["saved_facility_pct"] for o in opts], height=0.38, color=BLUE,
            label="hardware + AI (retrained where it matters)")
    for i, o in enumerate(opts):
        ax.text(o["saved_facility_pct"] + 0.1, i - 0.2, f"{o['saved_facility_pct']:.1f} % · {o['saved_tco2_yr']:g} tCO₂/yr · "
                f"payback {o['payback_years']:g} yr", va="center", fontsize=9, color=INK2)
    ax.set_yticks(list(y), [o["title"] for o in opts])
    ax.set_xlim(0, max(o["saved_facility_pct"] for o in opts) * 1.55)
    ax.set_xlabel("facility energy saved vs today's AI on today's room (%)")
    ax.grid(axis="y", visible=False)
    ax.legend(loc="lower right")
    ax.set_axisbelow(True)
    ax.set_title("Upgrade advisor: every option run in closed loop on the upgraded plant\n(no rack above 27 °C in any of them; "
                 "CAPEX are budget assumptions)", loc="left")
    fig.tight_layout()
    fig.savefig(DOCS / "upgrades.png", dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    bundle = pipeline.load(rebuild_if_stale=True)
    equipment = telemetry.load()
    architecture()
    agents_trace(AgentContext.from_bundle(bundle, equipment))
    hardware_trends(equipment)
    attacks(bundle)
    upgrades(bundle)
    print("wrote", ", ".join(p.name for p in sorted(DOCS.glob("*.png"))))
