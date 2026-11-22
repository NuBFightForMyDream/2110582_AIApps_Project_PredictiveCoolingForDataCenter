"""Phase 3: equipment catalog, flow balance, upgrade study / advisor and the Hardware Engineer's S8 plan."""
import pandas as pd
import pytest

from predictive_cooling import config as C
from predictive_cooling import pipeline, preprocess
from predictive_cooling.agents import AgentContext, CaseRequest, run_case
from predictive_cooling.agents.gemini import Call
from predictive_cooling.hardware import advisor, telemetry
from predictive_cooling.hardware.catalog import INSTALLED, INSTRUMENTS, UPGRADE_PRODUCTS
from predictive_cooling.hardware.diagnostics import EquipmentWindow, diagnose
from predictive_cooling.hardware.flows import balance
from predictive_cooling.hardware.registry import DEVICES
from predictive_cooling.hardware.upgrades import UPGRADES, economics
from predictive_cooling.plant import PlantParams

AT = "2026-04-29 05:30"


@pytest.fixture(scope="module")
def bundle():
    b = pipeline.load(rebuild_if_stale=False)
    if b is None:
        pytest.skip("artifacts/bundle.pkl missing or built with another scikit-learn; run python -m predictive_cooling.pipeline")
    return b


@pytest.fixture(scope="module")
def ctx(bundle):
    return AgentContext.from_bundle(bundle, telemetry.load())


# ---- catalog ------------------------------------------------------------------------------------
def test_every_device_has_an_installed_model_and_named_products_cite_a_source():
    assert {d.id for d in DEVICES} == set(INSTALLED)
    named = [p for p in INSTALLED.values() if p.vendor != "—"] + [p for _, p in INSTRUMENTS] + list(UPGRADE_PRODUCTS.values())
    assert named and all(p.source.startswith("https://") for p in named)
    assert all(key in UPGRADE_PRODUCTS for u in UPGRADES.values() for key in u.products)


def test_upgrade_effects_change_the_plant_as_described():
    base = PlantParams()
    assert UPGRADES["containment"].apply(base).recirc_c == tuple(r * 0.5 for r in base.recirc_c)
    assert UPGRADES["ec_fans"].apply(base).crah_fan_rated_kw == pytest.approx(base.crah_fan_rated_kw * 0.7)
    package = UPGRADES["package"].apply(base)
    assert package.cop_ref > base.cop_ref and package.ups_loss_fraction < base.ups_loss_fraction
    assert package.recirc_c[-1] < base.recirc_c[-1] and package.pump_tower_fraction < base.pump_tower_fraction


def test_economics_arithmetic():
    table = pd.DataFrame([{"upgrade": "ec_fans", "variant": "ai", "facility_kwh": 900.0, "cooling_kwh": 180.0}])
    out = economics(table, {"facility_kwh": 1000.0, "cooling_kwh": 200.0}, days=10, capex={"ec_fans": 36_500})
    row = out.iloc[0]
    assert row["saved_kwh_yr"] == pytest.approx(100 * 36.5)
    assert row["saved_thb_yr"] == pytest.approx(3650 * C.ELECTRICITY_THB_PER_KWH)
    assert row["saved_cooling_pct"] == pytest.approx(10.0) and row["payback_years"] == pytest.approx(2.5)


# ---- flows -------------------------------------------------------------------------------------
def test_flow_balance_closes():
    raw = pd.read_csv(C.DATA_PATH, parse_dates=["timestamp"], index_col="timestamp")
    clean, _ = preprocess.clean(raw)
    at = pd.Timestamp("2026-04-21 02:00")
    bal = balance(clean.loc[at], telemetry.load().loc[at])
    pw, heat = bal["power"], bal["heat"]
    parts = pw["it"] + pw["ups_loss"] + pw["lighting"] + pw["chiller"] + pw["crah_fans"] + pw["pumps_tower"]
    assert parts == pytest.approx(pw["facility"], abs=0.01)                  # sub-meters are logged to 0.001 kW
    assert sum(pw["groups"].values()) == pytest.approx(pw["it"])
    assert heat["rejected"] == pytest.approx(heat["chilled_water"] + heat["compressor"])
    assert 1.2 < bal["kpi"]["pue"] < 2.0 and 3 < bal["kpi"]["cop"] < 7


# ---- study + advisor ---------------------------------------------------------------------------
def test_upgrade_study_is_safe_and_ranked(bundle):
    study = bundle["upgrades"]
    assert (study["table"]["violation_minutes"] == 0).all()                     # no option overheats a rack
    plan = advisor.plan(study)
    paybacks = [o["payback_years"] for o in plan["options"]]
    assert paybacks == sorted(paybacks) and plan["options"][0]["key"] == "ups_ess"
    largest = max(plan["options"], key=lambda o: o["saved_kwh_yr"])
    assert largest["key"] == "package" and largest["saved_facility_pct"] > largest["hardware_only_facility_pct"]
    assert any("ceiling" in n for n in plan["notes"])                           # containment hits the 24 °C policy limit


def test_own_capex_changes_the_ranking(bundle):
    capex = {k: sum(u.capex_thb) / 2 for k, u in UPGRADES.items()} | {"ups_ess": 10_000_000}
    plan = advisor.plan(bundle["upgrades"], capex=capex)
    assert plan["options"][0]["key"] != "ups_ess"


def test_maintenance_comes_from_the_current_findings(bundle):
    diag = diagnose(EquipmentWindow(telemetry.load(), pd.Timestamp(AT)))
    codes = {m["code"] for m in advisor.plan(bundle["upgrades"], diag)["maintenance_first"]}
    assert {"FILTER_LOADING", "BEARING_WEAR"} <= codes


# ---- S8 in a case ------------------------------------------------------------------------------
def test_offline_upgrade_case(ctx):
    result = run_case(CaseRequest(at=AT, mode="upgrade"), ctx)
    assert result.status == "completed" and result.decision == "upgrade_plan", result.reason_codes
    assert all(c.passed for c in result.checks) and "S8" in {e.skill_id for e in result.events}
    assert "cooling_advisor" not in {e.actor for e in result.events} and result.command is None
    assert "Fastest payback" in result.explanation and result.evidence["upgrades"]["maintenance_first"]


def test_upgrade_plan_needs_the_study(bundle):
    bare = AgentContext.from_bundle({**bundle, "upgrades": None}, telemetry.load())
    result = run_case(CaseRequest(at=AT, mode="upgrade"), bare)
    assert result.status == "failed" and result.reason_codes == ["UPGRADE_STUDY_MISSING"]


def test_g3_rejects_an_edited_plan(ctx, monkeypatch):
    from predictive_cooling.agents import tools as T
    real, calls = T.evaluate_upgrades, {"n": 0}

    def edited_then_real(context, diag):
        calls["n"] += 1
        out = real(context, diag)
        if calls["n"] == 1:
            out = {**out, "options": [{**out["options"][0], "payback_years": 0.01}] + out["options"][1:]}
        return out
    monkeypatch.setattr(T, "evaluate_upgrades", edited_then_real)
    result = run_case(CaseRequest(at=AT, mode="upgrade"), ctx)
    assert result.status == "failed" and result.reason_codes == ["UPGRADE_EVIDENCE_MISMATCH"]


class Scripted:
    def __init__(self, script):
        self.script, self.index = script, {}

    def turn(self, role, instructions, history, tools, timeout):
        from predictive_cooling.agents.gemini import Turn
        i = self.index.get(role, 0)
        self.index[role] = i + 1
        return Turn([self.script[role][i]], tokens=10)


def _script(engineer):
    return {
        "supervisor": [Call("call_data_analyst"), Call("call_security_analyst"), Call("call_hardware_engineer"),
                       Call("finish_case", {"note": "Plan ready."})],
        "data_analyst": [Call("read_sensors"), Call("inspect_data_quality"), Call("summarize_state"), Call("forecast_hold"),
                         Call("finish_analysis", {"note": "Data ready."})],
        "security_analyst": [Call("check_sensor_integrity"), Call("audit_command_channel"),
                             Call("finish_security_review", {"note": "Trusted."})],
        "hardware_engineer": engineer,
    }


def test_gemini_upgrade_loop_with_scripted_provider(ctx, monkeypatch):
    provider = Scripted(_script([Call("read_equipment"), Call("diagnose_equipment"), Call("evaluate_upgrades"),
                                 Call("finish_equipment_check", {"note": "Filter first, then ESS."})]))
    monkeypatch.setattr("predictive_cooling.agents.gemini.provider_factory", lambda: provider)
    result = run_case(CaseRequest(at=AT, mode="upgrade", agent_mode="gemini"), ctx)
    assert result.status == "completed" and result.decision == "upgrade_plan", result.reason_codes
    assert result.model_calls == 16


def test_model_cannot_plan_upgrades_outside_upgrade_mode(ctx, monkeypatch):
    script = _script([Call("read_equipment"), Call("diagnose_equipment"), Call("evaluate_upgrades")])
    monkeypatch.setattr("predictive_cooling.agents.gemini.provider_factory", lambda: Scripted(script))
    result = run_case(CaseRequest(at=AT, mode="analyze", agent_mode="gemini"), ctx)
    assert result.reason_codes == ["TOOL_NOT_ALLOWED"]
