"""Typed contracts for one agent case (G1 validates the request before anything runs)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import config as C
from ..hardware.registry import TRIPPABLE


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CaseRequest(StrictModel):
    """One question about one moment in the room's sensor log."""
    at: datetime
    question: str = Field(default="What supply-air setpoint should we use for the next hour, and why?",
                          min_length=1, max_length=1000)
    mode: Literal["recommend", "analyze", "upgrade"] = "recommend"
    agent_mode: Literal["offline", "gemini", "claude"] = "offline"
    sensor_fault: tuple[str, ...] = Field(default=(), description="Demo: these racks' inlet sensors stop reporting "
                                                                   "for the last 45 minutes before `at`.")
    equipment_fault: tuple[str, ...] = Field(default=(), description="Demo: these cooling devices trip (status 0) "
                                                                      "for the last 30 minutes before `at`.")
    cyber_attack: Literal["none", "spoofing", "replay", "setpoint_tamper"] = Field(
        default="none", description="Demo: a simulated attack on the building network before `at` (see security/attacks.py).")

    @field_validator("at")
    @classmethod
    def on_grid(cls, value: datetime):
        if value.tzinfo is not None or value.minute % C.STEP_MINUTES or value.second or value.microsecond:
            raise ValueError("`at` must be a local timestamp on the 15-minute grid")
        return value

    @field_validator("sensor_fault")
    @classmethod
    def known_racks(cls, value):
        if len(set(value)) != len(value) or not set(value) <= set(C.RACKS):
            raise ValueError("sensor_fault must list distinct rack ids such as 'B6'")
        return value

    @field_validator("equipment_fault")
    @classmethod
    def known_devices(cls, value):
        if len(set(value)) != len(value) or not set(value) <= set(TRIPPABLE):
            raise ValueError("equipment_fault must list distinct devices from " + ", ".join(TRIPPABLE))
        return value


class Policy(StrictModel):
    version: str = "predictive-cooling-v3"
    inlet_limit_c: float = Field(default=C.INLET_LIMIT, ge=15, le=35)
    history_hours: float = Field(default=2.0, ge=1.5, le=6)
    equipment_history_days: float = Field(default=7.0, ge=1, le=14)   # hardware trends need days, not hours
    security_history_hours: float = Field(default=26.0, ge=2, le=72)  # replay check: the last day + the attack hour
    tool_budget: int = Field(default=30, ge=0, le=100)
    model_call_budget: int = Field(default=24, ge=0, le=40)
    deadline_seconds: float = Field(default=120, gt=0, le=600)


class Event(StrictModel):
    step: int
    actor: str
    action: str
    status: str
    skill_id: str | None = None
    detail: str = ""
    elapsed_ms: float
    hash: str = ""                # SHA-256 chain over the trace (security/audit.py)


class Check(StrictModel):
    name: str
    passed: bool
    detail: str = ""


Status = Literal["completed", "insufficient_data", "security_alert", "failed", "budget_exceeded"]
Decision = Literal["change", "no_change", "max_cooling", "fallback", "analysis_only", "upgrade_plan", "unavailable"]


class CaseResult(BaseModel):
    case_id: str
    at: datetime
    mode: str
    agent_mode: str
    workflow_mode: str = "offline_langgraph_roles"
    status: Status = "failed"
    decision: Decision = "unavailable"
    setpoint_in_use: float | None = None
    recommended_setpoint: float | None = None
    plan: list[float] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)       # tool outputs, recomputed by G3 before release
    checks: list[Check] = Field(default_factory=list)  # G3 verification list
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str = ""
    agent_notes: dict[str, str] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)
    security: dict = Field(default_factory=dict)       # G1 prompt screen, G4 output guard, audit-chain head
    command: dict | None = None                        # HMAC-signed recommendation (G4); None when nothing is released
    tool_calls: int = 0
    model_calls: int = 0
    model_tokens: int = 0
    elapsed_ms: float = 0.0
    execution: dict = Field(default_factory=dict)
