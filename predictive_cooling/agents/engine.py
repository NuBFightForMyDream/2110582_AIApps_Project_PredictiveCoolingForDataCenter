"""LangGraph orchestration of the three agents, the G2 tool gateway and G3 independent verification.

    G1 request + prompt screen  ->  Supervisor (S1)  ->  Data Analyst (S2, S3)  ->  Security Analyst (S7)
        ->  Hardware Engineer (S6)  ->  Cooling Advisor (S4)  ->  G3 re-read + recompute
        ->  Supervisor (S5) composes the answer  ->  G4 output guard, signed command, audit chain

Offline mode runs each role's procedure directly in a graph node (no LLM).
Gemini and Claude modes replace the five role nodes with real parent/child function-calling loops
(see llm_loops.py); all paths share the same tools, G2 gateway, G3 and S5.
"""
import hashlib
from importlib import import_module
import json
import logging
import time
from typing import TypedDict
from uuid import uuid4

import numpy as np
import pandas as pd
from langgraph.graph import END, START, StateGraph

from .. import config as C
from ..hardware.diagnostics import EquipmentWindow, summary_note
from ..safety import RULES
from ..security import commands as security_commands
from ..security.audit import GENESIS, link, verify_chain
from ..security.prompt_guard import screen_output, screen_question
from ..security.signing import digest, sign_command
from . import tools as T
from .models import CaseRequest, CaseResult, Check, Event, Policy
from .skills import SKILLS

LOG = logging.getLogger("predictive_cooling.agents")


class GuardError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Runtime:
    """Shared state of one case: request, evidence window, budgets and the event trace."""

    def __init__(self, request: CaseRequest, ctx: T.AgentContext, policy: Policy, case_id: str):
        self.request, self.ctx, self.policy = request, ctx, policy
        self.started = time.monotonic()
        self.result = CaseResult(case_id=case_id, at=request.at, mode=request.mode, agent_mode=request.agent_mode)
        self.window: T.CaseWindow | None = None
        self.equipment: EquipmentWindow | None = None
        self.security_window: T.CaseWindow | None = None
        self.ready = False
        self.trusted = True
        self.model_question = request.question                # what the LLM agents see (G1 may withhold it)
        self.proposal: float | None = None
        self.proposal_made = False
        self.on_event = None

    # -- trace ------------------------------------------------------------------------------
    def event(self, actor, action, status="passed", skill=None, detail=""):
        data = dict(step=len(self.result.events) + 1, actor=actor, action=action, status=status, skill_id=skill,
                    detail=detail, elapsed_ms=round((time.monotonic() - self.started) * 1000, 2))
        previous = self.result.events[-1].hash if self.result.events else GENESIS
        event = Event(**data, hash=link(previous, data))           # tamper-evident trace (security/audit.py)
        self.result.events.append(event)
        LOG.info(json.dumps(event.model_dump()))
        if self.on_event is not None:                  # live progress for a UI; never allowed to break a case
            try:
                self.on_event(event)
            except Exception:
                LOG.exception("on_event callback failed")

    def check_deadline(self):
        if time.monotonic() - self.started >= self.policy.deadline_seconds:
            raise GuardError("DEADLINE_EXCEEDED")

    def activate(self, skill_id, actor):
        self.check_deadline()
        skill = SKILLS[skill_id]
        if skill.owner != actor:
            raise GuardError("SKILL_OWNER_MISMATCH")
        self.event(actor, "skill_loaded", skill=skill_id, detail=f"{skill.name} · v{skill.version}")
        return skill.instructions()

    # -- G2: every tool call and every delegation goes through here -------------------------
    def call(self, tool, actor, skill_id, function):
        self.check_deadline()
        skill = SKILLS[skill_id]
        if skill.owner != actor or tool not in skill.tools:
            self.event("G2", tool, "rejected", skill_id, "TOOL_NOT_ALLOWED")
            raise GuardError("TOOL_NOT_ALLOWED")
        if self.result.tool_calls >= self.policy.tool_budget:
            self.event("G2", tool, "rejected", skill_id, "TOOL_BUDGET_EXCEEDED")
            raise GuardError("TOOL_BUDGET_EXCEEDED")
        self.result.tool_calls += 1          # reserved before running, nested delegations included
        self.event("G2", tool, "authorized", skill_id, f"{actor} · window ends {self.request.at:%d %b %H:%M}")
        try:
            value = function()
            self.check_deadline()
        except GuardError:
            raise
        except Exception as exc:
            self.event(actor, tool, "failed", skill_id, type(exc).__name__)
            raise
        self.event(actor, tool, "completed", skill_id, _summary(tool, value))
        return value


def _summary(tool, value):
    if not isinstance(value, dict):
        return ""
    if tool == "inspect_data_quality":
        return "ready" if value["ready"] else "not ready: " + ", ".join(value["errors"][:4])
    if tool == "summarize_state":
        return f"hottest {value['hottest_rack']} {value['hottest_inlet_c']} °C, headroom {value['headroom_to_limit_c']} °C"
    if tool == "forecast_hold":
        return f"hold {value['hold_setpoint_c']:g} °C → peak {max(value['with_safety_margin_c']):.2f} °C incl. margin"
    if tool == "run_mpc":
        return f"{value['safe_plans']}/{value['plans_tried']} safe; cheapest {value['chosen_plan_c']}"
    if tool == "check_safety":
        return f"{value['proposed_c']:g} → {value['final_c']:g} °C" + (f" ({', '.join(value['rules_fired'])})" if value["rules_fired"] else "")
    if tool == "propose_setpoint":
        return f"proposed {value['proposed_setpoint_c']}"
    if tool == "read_equipment":
        lost = value["comm_loss"]
        return f"{value['devices_polled'] - len(lost)}/{value['devices_polled']} devices answered" + (f"; no answer: {', '.join(lost)}" if lost else "")
    if tool == "diagnose_equipment":
        return f"{value['overall']} · constraint {value['constraint']} · {len(value['findings'])} finding(s)"
    if tool == "call_hardware_engineer":
        return f"constraint {value['constraint']}"
    if tool in ("check_sensor_integrity", "audit_command_channel"):
        return "ok" if value["trusted"] else ", ".join(f["code"] for f in value["findings"])
    if tool == "call_security_analyst":
        return value["verdict"]
    return ""


# -- shared tool implementations (used by both offline and Gemini roles) ---------------------
def tool_impl(rt: Runtime, name: str, args=None):
    win, ctx = rt.window, rt.ctx
    if name == "check_sensor_integrity":               # security and hardware tools do not depend on data readiness
        out = rt.result.evidence["integrity"] = T.check_sensor_integrity(rt.security_window, rt.equipment, ctx)
        return out
    if name == "audit_command_channel":
        if "integrity" not in rt.result.evidence:
            raise GuardError("INTEGRITY_NOT_CHECKED")
        out = rt.result.evidence["command_audit"] = T.audit_command_channel(rt.security_window, rt.equipment)
        return out
    if name == "read_equipment":
        out = T.read_equipment(rt.equipment)
        rt.result.evidence["equipment_read"] = {k: out[k] for k in ("devices_polled", "comm_loss", "bad_quality_points")}
        return out
    if name == "diagnose_equipment":
        if "equipment_read" not in rt.result.evidence:
            raise GuardError("EQUIPMENT_NOT_READ")
        out = rt.result.evidence["equipment"] = T.diagnose_equipment(rt.equipment)
        return out
    if name == "read_sensors":
        return T.read_sensors(win)
    if name == "inspect_data_quality":
        out = T.inspect_data_quality(win)
        rt.result.evidence["data_quality"] = out
        return out
    if win.clean is None or rt.result.evidence.get("data_quality", {}).get("ready") is not True:
        raise GuardError("DATA_NOT_INSPECTED")
    if name == "summarize_state":
        out = rt.result.evidence["state"] = T.summarize_state(win)
        return out
    if name == "forecast_hold":
        out = rt.result.evidence["forecast_hold"] = T.forecast_hold(win, ctx)
        return out
    if name == "run_mpc":
        out = rt.result.evidence["mpc"] = T.run_mpc(win, ctx)
        return out
    if name == "check_safety":
        if "equipment" not in rt.result.evidence:
            raise GuardError("EQUIPMENT_NOT_INSPECTED")
        out = rt.result.evidence["safety"] = T.check_safety(win, ctx, args["setpoint"], equipment_constraint(rt))
        return out
    raise GuardError("UNKNOWN_TOOL")


# -- offline role procedures -------------------------------------------------------------------
class GraphState(TypedDict, total=False):
    runtime: Runtime


def supervisor_plan(state):
    rt = state["runtime"]
    rt.activate("S1", "supervisor")
    route = "Data Analyst" + (" → Cooling Advisor if data is ready" if rt.request.mode == "recommend" else " only (analyze)")
    rt.event("supervisor", "plan", detail=route)
    return {}


def data_analyst(state):
    rt = state["runtime"]

    def work():
        rt.activate("S2", "data_analyst")
        rt.call("read_sensors", "data_analyst", "S2", lambda: tool_impl(rt, "read_sensors"))
        quality = rt.call("inspect_data_quality", "data_analyst", "S2", lambda: tool_impl(rt, "inspect_data_quality"))
        rt.activate("S3", "data_analyst")
        if quality["ready"]:
            rt.call("summarize_state", "data_analyst", "S3", lambda: tool_impl(rt, "summarize_state"))
            hold = rt.call("forecast_hold", "data_analyst", "S3", lambda: tool_impl(rt, "forecast_hold"))
            note = f"Data ready. Holding {hold['hold_setpoint_c']:g} °C looks {'safe' if hold['holding_is_safe'] else 'unsafe'} for the next hour."
        else:
            note = "Data not ready: " + ", ".join(quality["errors"])
        rt.call("finish_analysis", "data_analyst", "S3", lambda: {"ready": quality["ready"]})
        rt.result.agent_notes["data_analyst"] = note
        return quality["ready"]

    rt.ready = rt.call("call_data_analyst", "supervisor", "S1", work)
    rt.event("supervisor", "receive_analysis", "completed" if rt.ready else "blocked")
    return {}


def finish_security(rt: Runtime, note: str):
    """The Security Analyst's report to the Supervisor. The verdict is Python's, not the model's."""
    ev = rt.result.evidence
    sec = ev["security"] = security_commands.verdict(ev["integrity"], ev["command_audit"], rt.result.security.get("request_screen"))
    rt.trusted = sec["trusted"]
    rt.result.agent_notes["security_analyst"] = note
    return {"verdict": sec["verdict"], "codes": sec["codes"],
            "findings": [{k: f[k] for k in ("code", "severity", "detail", "action")} for f in sec["findings"]]}


def security_analyst(state):
    rt = state["runtime"]

    def work():
        rt.activate("S7", "security_analyst")
        rt.call("check_sensor_integrity", "security_analyst", "S7", lambda: tool_impl(rt, "check_sensor_integrity"))
        rt.call("audit_command_channel", "security_analyst", "S7", lambda: tool_impl(rt, "audit_command_channel"))
        ev = rt.result.evidence
        note = security_commands.summary_note(security_commands.verdict(ev["integrity"], ev["command_audit"],
                                                                        rt.result.security.get("request_screen")))
        return rt.call("finish_security_review", "security_analyst", "S7", lambda: finish_security(rt, note))

    report = rt.call("call_security_analyst", "supervisor", "S1", work)
    rt.event("supervisor", "receive_security_report", "completed" if report["verdict"] == "trusted" else "blocked",
             detail=report["verdict"] + (": " + ", ".join(report["codes"]) if report["codes"] else ""))
    return {}


def equipment_constraint(rt: Runtime) -> str:
    return rt.result.evidence.get("equipment", {}).get("constraint", "none")


def finish_hardware(rt: Runtime, note: str):
    """The Hardware Engineer's report to the Supervisor: constraint + the findings behind it."""
    eq = rt.result.evidence["equipment"]
    rt.result.agent_notes["hardware_engineer"] = note
    return {"overall": eq["overall"], "constraint": eq["constraint"], "constraint_reasons": eq["constraint_reasons"],
            "findings": [{k: f[k] for k in ("device", "code", "severity", "value", "unit", "days_to_next", "action")}
                         for f in eq["findings"][:5]]}


def hardware_engineer(state):
    rt = state["runtime"]

    def work():
        rt.activate("S6", "hardware_engineer")
        rt.call("read_equipment", "hardware_engineer", "S6", lambda: tool_impl(rt, "read_equipment"))
        diag = rt.call("diagnose_equipment", "hardware_engineer", "S6", lambda: tool_impl(rt, "diagnose_equipment"))
        return rt.call("finish_equipment_check", "hardware_engineer", "S6", lambda: finish_hardware(rt, summary_note(diag)))

    report = rt.call("call_hardware_engineer", "supervisor", "S1", work)
    rt.event("supervisor", "receive_hardware_report", "completed", detail=f"{report['overall']} · constraint {report['constraint']}")
    return {}


def cooling_advisor(state):
    rt = state["runtime"]

    def work():
        rt.activate("S4", "cooling_advisor")
        mpc = rt.call("run_mpc", "cooling_advisor", "S4", lambda: tool_impl(rt, "run_mpc"))
        safety = rt.call("check_safety", "cooling_advisor", "S4",
                         lambda: tool_impl(rt, "check_safety", {"setpoint": mpc["first_step_c"]}))
        rt.call("propose_setpoint", "cooling_advisor", "S4", lambda: propose(rt, safety["final_c"]))
        rt.result.agent_notes["cooling_advisor"] = (f"Cheapest safe plan {mpc['chosen_plan_c']} of {mpc['safe_plans']} safe plans; "
                                                    f"safety filter returned {safety['final_c']:g} °C"
                                                    f" (hardware constraint {safety['equipment_constraint']}).")

    rt.call("call_cooling_advisor", "supervisor", "S1", work)
    rt.event("supervisor", "receive_proposal", "completed")
    return {}


def propose(rt: Runtime, setpoint):
    rt.proposal = None if setpoint is None else float(setpoint)
    rt.proposal_made = True
    return {"proposed_setpoint_c": rt.proposal, "requires_independent_g3_validation": True}


# -- G3: re-read, recompute, compare -----------------------------------------------------------
def validate(state):
    rt = state["runtime"]
    rt.check_deadline()
    checks = rt.result.checks
    fresh = T.CaseWindow(rt.ctx.log, pd.Timestamp(rt.request.at), rt.policy.history_hours, rt.request.sensor_fault,
                         rt.request.cyber_attack)
    quality = T.inspect_data_quality(fresh)               # authoritative re-read, not the agent's copy
    rt.result.setpoint_in_use = fresh.setpoint_in_use
    checks.append(Check(name="Sensor data re-read and re-inspected", passed=quality["ready"],
                        detail="ready" if quality["ready"] else ", ".join(quality["errors"])))
    if quality["ready"] != rt.ready:
        raise GuardError("EVIDENCE_CHANGED")
    trusted = verify_security(rt)
    constraint = verify_hardware(rt)
    if not trusted:
        rt.result.status, rt.result.decision = "security_alert", "fallback"
        rt.result.reason_codes = rt.result.evidence["security"]["codes"]
        rt.result.recommended_setpoint = T.fallback_step(fresh, rt.ctx, "fallback")
        rt.result.evidence["data_quality"] = quality
        rt.event("G3", "validate_evidence", "blocked", detail="AI withheld; safety rule R6: untrusted data")
        return {}
    if not quality["ready"]:
        rt.result.status, rt.result.decision = "insufficient_data", "fallback"
        rt.result.reason_codes = quality["errors"]
        rt.result.recommended_setpoint = T.fallback_step(fresh, rt.ctx, constraint)
        rt.result.evidence["data_quality"] = quality
        rt.event("G3", "validate_evidence", "blocked", detail="AI withheld; safety rule R1 fallback applies")
        return {}
    state_now = T.summarize_state(fresh)
    reported = rt.result.evidence.get("state")
    same = reported is not None and all(reported[k] == state_now[k] for k in ("hottest_rack", "hottest_inlet_c", "it_power_kw"))
    checks.append(Check(name="Analyst's numbers match recomputation", passed=same,
                        detail=f"hottest {state_now['hottest_rack']} {state_now['hottest_inlet_c']} °C"))
    if not same:
        raise GuardError("ANALYSIS_EVIDENCE_MISMATCH")
    rt.result.evidence["state"] = state_now
    rt.result.evidence["forecast_hold"] = T.forecast_hold(fresh, rt.ctx)
    if rt.request.mode == "analyze":
        rt.result.status, rt.result.decision = "completed", "analysis_only"
        rt.event("G3", "validate_analysis", detail="Analysis only; no setpoint released")
        return {}
    expected, reason, table, safety = T.expected_recommendation(fresh, rt.ctx, constraint)
    rt.result.evidence["mpc"] = T.run_mpc(fresh, rt.ctx)
    rt.result.evidence["safety"] = safety
    rt.result.evidence["_plans"] = table
    checks.append(Check(name="A proposal was made", passed=rt.proposal_made))
    match = rt.proposal_made and rt.proposal is not None and abs(rt.proposal - expected) < 1e-9
    checks.append(Check(name="Proposal = recomputed MPC + safety filter", passed=match,
                        detail=f"proposed {rt.proposal}, recomputed {expected:g} °C"))
    if not match:
        raise GuardError("PROPOSAL_EVIDENCE_MISMATCH")
    in_range = C.SP_MIN <= expected <= C.SP_MAX and abs(expected - fresh.setpoint_in_use) <= 2
    checks.append(Check(name="Within 16–24 °C and rate limit", passed=in_range))
    if not in_range:
        raise GuardError("SETPOINT_OUT_OF_POLICY")
    respects = constraint == "none" or expected <= fresh.setpoint_in_use
    checks.append(Check(name="Hardware constraint respected (R5)", passed=respects,
                        detail=f"constraint {constraint}" + (": no warmer than "
                                                              f"{fresh.setpoint_in_use:g} °C" if constraint != "none" else "")))
    if not respects:
        raise GuardError("SETPOINT_OUT_OF_POLICY")
    chosen = table[table["chosen"]].iloc[0]
    safe_plan = bool(chosen["safe"])
    checks.append(Check(name="Chosen plan forecast ≤ 27 °C incl. margin", passed=safe_plan,
                        detail=f"peak {chosen['peak_guarded_c']:.2f} °C"))
    rt.result.plan = [float(chosen[f"sp_{k}"]) for k in range(1, C.HORIZON + 1)]
    rt.result.recommended_setpoint = expected
    rt.result.status = "completed"
    if reason == "no_safe_plan_max_cooling":
        rt.result.decision = "max_cooling"
    else:
        rt.result.decision = "no_change" if expected == fresh.setpoint_in_use else "change"
    rt.event("G3", "validate_recommendation", detail=f"approved {expected:g} °C")
    return {}


def verify_security(rt: Runtime) -> bool:
    """G3 for the security layer: rebuild the windows, re-run both checks, compare with the analyst's report."""
    at = pd.Timestamp(rt.request.at)
    room = T.CaseWindow(rt.ctx.log, at, rt.policy.security_history_hours, rt.request.sensor_fault, rt.request.cyber_attack)
    equipment = EquipmentWindow(rt.ctx.equipment, at, rt.policy.equipment_history_days, rt.request.equipment_fault,
                                rt.request.cyber_attack)
    sec = security_commands.verdict(T.check_sensor_integrity(room, equipment, rt.ctx), T.audit_command_channel(room, equipment),
                                    rt.result.security.get("request_screen"))
    reported = rt.result.evidence.get("security")
    same = reported is not None and reported["verdict"] == sec["verdict"] and reported["codes"] == sec["codes"]
    rt.result.checks.append(Check(name="Data integrity re-checked (forgery, replay, setpoint writes)", passed=same and sec["trusted"],
                                  detail=sec["verdict"] + (": " + ", ".join(sec["codes"]) if sec["codes"] else "")))
    if not same:
        raise GuardError("SECURITY_EVIDENCE_MISMATCH")
    rt.result.evidence["security"] = sec
    return sec["trusted"]


def verify_hardware(rt: Runtime) -> str:
    """G3 for the hardware layer: re-poll every device, re-run the diagnosis, compare with what the engineer reported."""
    fresh = EquipmentWindow(rt.ctx.equipment, pd.Timestamp(rt.request.at), rt.policy.equipment_history_days,
                            rt.request.equipment_fault, rt.request.cyber_attack)
    diag = T.diagnose_equipment(fresh)
    reported = rt.result.evidence.get("equipment")
    codes = lambda d: [(f["device"], f["code"], f["severity"]) for f in d["findings"]]  # noqa: E731
    same = reported is not None and reported["constraint"] == diag["constraint"] and codes(reported) == codes(diag)
    rt.result.checks.append(Check(name="Hardware re-polled and re-diagnosed", passed=same,
                                  detail=f"{diag['devices_answering']}/{diag['devices_polled']} devices · {diag['overall']} · "
                                         f"constraint {diag['constraint']}"))
    if not same:
        raise GuardError("EQUIPMENT_EVIDENCE_MISMATCH")
    rt.result.evidence["equipment"] = diag
    return diag["constraint"]


# -- S5: deterministic statement ---------------------------------------------------------------
def supervisor_finalize(state):
    rt = state["runtime"]
    rt.activate("S5", "supervisor")
    r, ev = rt.result, rt.result.evidence
    mock = "Mock 12-rack room and simplified plant model; nothing was sent to equipment."
    hw = f"Hardware: {summary_note(ev['equipment'])}" if "equipment" in ev else ""
    sec = ev.get("security")
    security = "" if sec is None else ("Security: integrity checks passed." if not sec["findings"]
                                       else "Security: " + security_commands.summary_note(sec))
    if r.status == "security_alert":
        r.explanation = (f"No AI recommendation: the sensor data cannot be trusted. {security_commands.summary_note(sec)} "
                         f"Safety rule R6 applies: while the data is untrusted the room is never run warmer than now or than "
                         f"the proven fallback setpoint {rt.ctx.fallback_sp:g} °C — {r.recommended_setpoint:g} °C this step "
                         f"(from {r.setpoint_in_use:g} °C, at most 1 °C per 15 min). Alert the security team. {hw} {mock}")
    elif r.status == "insufficient_data":
        r.explanation = (f"No AI recommendation: {', '.join(r.reason_codes)}. Safety rule R1 applies — return toward the proven "
                         f"fallback setpoint {rt.ctx.fallback_sp:g} °C ({r.recommended_setpoint:g} °C this step, max 1 °C per 15 min). "
                         f"{security} {hw} {mock}")
    elif r.status == "completed":
        s, hold = ev["state"], ev["forecast_hold"]
        risk = (f"Holding {hold['hold_setpoint_c']:g} °C for the next hour is forecast to peak at "
                f"{max(hold['with_safety_margin_c']):.1f} °C incl. safety margin ({'safe' if hold['holding_is_safe'] else 'too close to 27 °C'}).")
        now = (f"Hottest rack {s['hottest_rack']} is {s['hottest_inlet_c']:.1f} °C ({s['headroom_to_limit_c']:.1f} °C below the limit), "
               f"IT {s['it_power_kw']:.0f} kW, cooling {s['cooling_kw']:.0f} kW.")
        if r.mode == "analyze":
            r.explanation = f"{now} {risk} {security} {hw} {mock}"
        else:
            m, safety = ev["mpc"], ev["safety"]
            head = {"change": f"Change the supply-air setpoint from {r.setpoint_in_use:g} °C to {r.recommended_setpoint:g} °C now.",
                    "no_change": f"Keep the supply-air setpoint at {r.recommended_setpoint:g} °C.",
                    "max_cooling": f"No plan is forecast to stay safe: cool to {r.recommended_setpoint:g} °C now (maximum cooling)."}[r.decision]
            saving = m["hold_energy_next_hour_kwh"] - m["chosen_energy_next_hour_kwh"]
            if abs(saving) < 0.05:
                versus = "the same as holding"
            elif saving > 0:
                versus = f"{saving:.1f} kWh less than holding"
            else:
                versus = f"{-saving:.1f} kWh more than holding" + ("" if m["hold_is_safe"] else ", the price of staying below the limit")
            plan = " → ".join(f"{v:g}" for v in r.plan)
            rules = "; ".join(f"{rid.split('_')[0]} {RULES[rid]}" for rid in safety["rules_fired"]) or "no rule had to step in"
            if r.plan and r.plan[0] != r.recommended_setpoint:
                rules += f" (the plan's first step {r.plan[0]:g} °C became {r.recommended_setpoint:g} °C)"
            r.explanation = (f"{head} {now} {risk} Of {m['plans_tried']} plans, {m['safe_plans']} stay safe; the cheapest is "
                             f"{plan} °C, forecast to use {m['chosen_energy_next_hour_kwh']:.1f} kWh next hour "
                             f"({versus}). Safety filter: {rules}. {security} {hw} G3 re-read the sensors, re-polled the "
                             f"hardware and recomputed this independently. {mock}")
    else:
        r.explanation = "No recommendation was released: " + ", ".join(r.reason_codes)
    rt.event("supervisor", "compose", "completed", "S5")
    return {}


# -- G4: what leaves the system ----------------------------------------------------------------
RELEASABLE = ("change", "no_change", "max_cooling", "fallback")


def release(state):
    """Screen model-written notes, then sign the recommendation an actuator gateway could verify."""
    rt = state["runtime"]
    r = rt.result
    found = {}
    for role, note in list(r.agent_notes.items()):
        r.agent_notes[role], hits = screen_output(note)
        if hits:
            found[role] = hits
    r.security["output_guard"] = {"notes_screened": len(r.agent_notes), "redactions": found}
    if r.recommended_setpoint is not None and r.decision in RELEASABLE:
        evidence = {k: v for k, v in r.evidence.items() if not k.startswith("_")}
        r.command = sign_command(r.case_id, f"{r.at:%Y-%m-%d %H:%M}", r.recommended_setpoint, r.decision,
                                 digest(json.loads(json.dumps(evidence, default=_plain))), rt.policy.version)
    detail = (f"notes screened{' · redacted ' + str(sum(map(len, found.values()))) if found else ''}; "
              + (f"signed {r.command['key_id']} · valid 15 min" if r.command else "nothing to sign"))
    rt.event("G4", "release", "passed", detail=detail)
    return {}


def _plain(o):
    return o.item() if isinstance(o, np.generic) else str(o)


def build_graph():
    builder = StateGraph(GraphState)
    builder.add_node("supervisor_plan", supervisor_plan)
    builder.add_node("data_analyst", data_analyst)
    builder.add_node("security_analyst", security_analyst)
    builder.add_node("hardware_engineer", hardware_engineer)
    builder.add_node("cooling_advisor", cooling_advisor)
    # Imported only when a live case runs. agent_mode is "gemini" or "claude" here, the name of the provider module.
    builder.add_node("llm_agents", lambda s: import_module(f".{s['runtime'].request.agent_mode}", __package__).run_agents(s["runtime"]))
    builder.add_node("guardrail_g3", validate)
    builder.add_node("supervisor_finalize", supervisor_finalize)
    builder.add_node("guardrail_g4", release)
    builder.add_conditional_edges(START, lambda s: "supervisor_plan" if s["runtime"].request.agent_mode == "offline" else "llm_agents")
    builder.add_edge("supervisor_plan", "data_analyst")
    builder.add_edge("data_analyst", "security_analyst")             # integrity and hardware are checked even when
    builder.add_edge("security_analyst", "hardware_engineer")        # the rack data is not ready
    builder.add_conditional_edges("hardware_engineer", lambda s: "cooling_advisor" if s["runtime"].ready and s["runtime"].trusted
                                  and s["runtime"].request.mode == "recommend" else "guardrail_g3")
    builder.add_edge("cooling_advisor", "guardrail_g3")
    builder.add_edge("llm_agents", "guardrail_g3")
    builder.add_edge("guardrail_g3", "supervisor_finalize")
    builder.add_edge("supervisor_finalize", "guardrail_g4")
    builder.add_edge("guardrail_g4", END)
    return builder.compile()


GRAPH = build_graph()


def run_case(request: CaseRequest, ctx: T.AgentContext | None = None, policy: Policy | None = None,
             case_id: str | None = None, on_event=None) -> CaseResult:
    """`on_event(event)` is called after every trace event (e.g. to show live progress); it cannot change the case."""
    ctx = ctx or T.default_context()
    # A live LLM needs ~10-12 sequential calls (plus retries on 429/503), so live modes get a longer deadline.
    policy = policy or (Policy() if request.agent_mode == "offline" else Policy(deadline_seconds=300))
    rt = Runtime(request, ctx, policy, case_id or uuid4().hex[:12])
    rt.on_event = on_event
    rt.result.execution = {"policy": policy.model_dump(), "request": request.model_dump(mode="json"),
                           "skills": {sid: {"version": s.version, "sha256": hashlib.sha256(s.instructions().encode()).hexdigest()[:16]}
                                      for sid, s in SKILLS.items()}}
    try:
        screen = rt.result.security["request_screen"] = screen_question(request.question)   # G1: prompt screen
        if screen["verdict"] == "blocked":
            rt.event("G1", "screen_request", "blocked", detail="prompt injection: " + ", ".join(m["category"] for m in screen["matches"]))
            raise GuardError("PROMPT_INJECTION_BLOCKED")
        if screen["verdict"] == "flagged":
            rt.model_question = ("[operator text withheld by the G1 prompt screen] What supply-air setpoint should we use "
                                 "for the next hour, and why?")
        rt.event("G1", "screen_request", "passed" if screen["verdict"] == "clean" else "flagged",
                 detail=f"{screen['verdict']} (score {screen['score']})")
        at = pd.Timestamp(request.at)                                  # G1: scope and request checks
        first, last = ctx.log.index.min(), ctx.log.index.max()
        if not first + pd.Timedelta(hours=policy.history_hours) <= at <= last:
            raise GuardError("CASE_TIME_OUTSIDE_SENSOR_LOG")
        if at not in ctx.equipment.index:
            raise GuardError("CASE_TIME_OUTSIDE_EQUIPMENT_LOG")
        rt.equipment = EquipmentWindow(ctx.equipment, at, policy.equipment_history_days, request.equipment_fault,
                                       request.cyber_attack)
        rt.window = T.CaseWindow(ctx.log, at, policy.history_hours, request.sensor_fault, request.cyber_attack)
        rt.security_window = T.CaseWindow(ctx.log, at, policy.security_history_hours, request.sensor_fault, request.cyber_attack)
        rt.event("G1", "validate_request", detail=f"{request.mode} · {request.agent_mode} · room zone-a · tools see "
                                                   f"{policy.history_hours:g} h of sensors and {policy.equipment_history_days:g} "
                                                   f"days of equipment data up to {at:%d %b %H:%M}")
        GRAPH.invoke({"runtime": rt}, config={"recursion_limit": 16})
    except GuardError as exc:
        r = rt.result
        r.status = ("budget_exceeded" if exc.code.endswith("BUDGET_EXCEEDED") or exc.code == "DEADLINE_EXCEEDED"
                    else "security_alert" if exc.code.startswith("PROMPT_INJECTION") else "failed")
        r.decision, r.recommended_setpoint, r.plan = "unavailable", None, []
        r.reason_codes = [exc.code]
        r.explanation = "No recommendation was released: " + exc.code
        if exc.code == "PROMPT_INJECTION_BLOCKED":
            found = ", ".join(m["category"] for m in r.security["request_screen"]["matches"])
            r.explanation = (f"G1 blocked the operator question as a likely prompt injection ({found}); no agent ran and "
                             "nothing was released. Rephrase it as a question about the room.")
        rt.event("workflow", "stop", "blocked", detail=exc.code)
    except Exception as exc:                                           # provider/config failures never look like success
        r = rt.result
        r.status, r.decision, r.recommended_setpoint, r.plan = "failed", "unavailable", None, []
        r.reason_codes = [str(exc) if str(exc) in ("GEMINI_NOT_CONFIGURED", "CLAUDE_NOT_CONFIGURED") else "WORKFLOW_ERROR"]
        r.explanation = "The workflow failed; no recommendation was released (" + r.reason_codes[0] + ")."
        rt.event("workflow", "stop", "failed", detail=type(exc).__name__)
    rt.result.elapsed_ms = round((time.monotonic() - rt.started) * 1000, 2)
    intact, _ = verify_chain([e.model_dump() for e in rt.result.events])
    rt.result.security["audit"] = {"events": len(rt.result.events), "head": rt.result.events[-1].hash if rt.result.events else GENESIS,
                                   "intact": intact}
    return rt.result


def plans_table(result: CaseResult):
    """The 81-plan table G3 verified (for charts); not part of the JSON result."""
    return result.evidence.get("_plans")


def to_json(result: CaseResult) -> dict:
    data = result.model_dump(mode="json", exclude={"evidence"})
    data["evidence"] = {k: v for k, v in result.evidence.items() if not k.startswith("_")}
    return json.loads(json.dumps(data, default=lambda o: o.item() if isinstance(o, np.generic) else str(o)))
