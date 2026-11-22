"""Hardware layer: point map, sensor gateway, equipment historian, diagnostics, rule R5 and the Hardware Engineer."""
import pandas as pd
import pytest
from pydantic import ValidationError

from predictive_cooling import config as C
from predictive_cooling import dataset, forecast, preprocess
from predictive_cooling.agents import AgentContext, CaseRequest, run_case
from predictive_cooling.hardware import telemetry
from predictive_cooling.hardware.diagnostics import EquipmentWindow, diagnose
from predictive_cooling.hardware.gateway import Gateway, SimulatedFieldBus, decode, encode
from predictive_cooling.hardware.registry import DEVICES, REGISTRY, TRIPPABLE, Point
from predictive_cooling.safety import SafetyFilter


@pytest.fixture(scope="module")
def tel():
    return telemetry.load()


@pytest.fixture(scope="module")
def ctx(tel):
    raw = dataset.load()
    clean, _ = preprocess.clean(raw)
    train, val, _ = preprocess.split(clean)
    gbm = forecast.Forecaster("gbm").fit(train)
    return AgentContext(raw, gbm, forecast.safety_margins(gbm, val), fallback_sp=20.0, equipment=tel)


def diag(tel, at, trips=()):
    return diagnose(EquipmentWindow(tel, pd.Timestamp(at), trips=trips))


def codes(d):
    return {(f["device"], f["code"]): f for f in d["findings"]}


# ---- registry + gateway ------------------------------------------------------------------------
def test_registry_covers_the_room():
    assert len(DEVICES) == 22 and len({d.id for d in DEVICES}) == 22
    assert {d.protocol for d in DEVICES} == {"BACnet/IP", "Modbus TCP", "SNMP v3"}
    assert sorted(d.id[4:] for d in DEVICES if d.kind == "pdu") == sorted(C.RACKS)
    for device_id in TRIPPABLE:
        assert REGISTRY[device_id].cooling_path and any(p.name == "status" for p in REGISTRY[device_id].points)


def test_gateway_decodes_registers_and_flags_bad_values():
    temp = Point("t", "°C", "HR 1", "int16", 0.1, (5, 40))
    assert encode(temp, 23.46) == 235 and decode(temp, 235) == (23.5, "good")       # 0.1 °C resolution on the wire
    assert decode(temp, 850) == (None, "out_of_range")                              # an 85 °C glitch is not trusted
    assert decode(temp, encode(temp, 1e9)) == (None, "out_of_range")                # saturated register
    status = Point("status", "", "HR 2", "uint16", 1, (0, 1))
    assert decode(status, encode(status, 0.0)) == (0, "good")                       # 0 is a real reading, not overflow
    real = Point("f", "m³/h", "AI:6", "real", valid=(0, 60000))
    assert decode(real, encode(real, 25123.4))[0] == pytest.approx(25123.4, abs=0.01)
    assert decode(temp, None) == (None, "no_data")


def test_gateway_reports_comm_loss(tel):
    gateway = Gateway(SimulatedFieldBus(tel))
    lost = gateway.poll("CT-1", "2026-04-26 15:00")                                 # tower controller offline
    assert lost["comm"] == "comm_loss" and set(lost["quality"].values()) == {"comm_loss"}
    ok = gateway.poll("CRAH-1", "2026-04-21 00:30")
    assert ok["comm"] == "ok" and set(ok["quality"].values()) == {"good"}
    table = gateway.point_table("UPS-1", "2026-04-21 00:30")
    assert "upsOutputPercentLoad" in " ".join(table["Address"])                     # RFC 1628 UPS-MIB


# ---- historian ---------------------------------------------------------------------------------
def test_telemetry_agrees_with_the_room_log(tel):
    raw = dataset.load()
    assert list(tel.columns) == [c for d in DEVICES for c in d.columns]
    common = raw.index.intersection(tel.index)
    pdu = tel.loc[common, [REGISTRY[f"PDU-{r}"].column("power_kw") for r in C.RACKS]].sum(axis=1)
    assert ((pdu - raw.loc[common, "it_power_kw"]).abs() / raw.loc[common, "it_power_kw"]).median() < 0.01
    assert (tel["CRAH-1.setpoint_c"].shift(-1).loc[common] == raw.loc[common, "crah_setpoint_c"]).mean() > 0.99
    assert (tel["CH-1.chwr_c"] > tel["CH-1.chws_c"]).all()                          # the water warms up in the room
    assert (tel["CH-1.cond_out_c"] > tel["CH-1.cond_in_c"]).all()
    assert (tel["CT-1.cold_water_c"].dropna() > tel["CT-1.wet_bulb_c"].dropna()).all()   # a tower cannot beat wet bulb


# ---- diagnostics -------------------------------------------------------------------------------
@pytest.mark.parametrize("at", ["2026-02-16 03:00", "2026-03-04 14:00", "2026-03-25 01:30", "2026-04-08 16:45",
                                "2026-04-14 23:00"])
def test_healthy_weeks_raise_no_alarm(tel, at):
    d = diag(tel, at)
    assert d["overall"] == "ok" and d["constraint"] == "none" and d["capacity"]["n_plus_1"]


def test_filter_loading_is_seen_days_before_the_limit(tel):
    f = codes(diag(tel, "2026-04-25 12:00"))[("CRAH-2", "FILTER_LOADING")]
    assert f["severity"] == "watch" and 0 < f["days_to_next"] <= 7 and f["next_limit"] == 250
    late = diag(tel, "2026-04-29 05:30")
    assert codes(late)[("CRAH-2", "FILTER_LOADING")]["severity"] == "warning"
    assert ("CRAH group", "REDUNDANCY_LOST") in codes(late)                         # one CRAH alone is too small now
    assert late["constraint"] == "no_raise"


def test_pump_bearing_critical_but_standby_ready_means_no_raise(tel):
    d = diag(tel, "2026-05-02 12:00")
    f = codes(d)[("CHWP-1", "BEARING_WEAR")]
    assert f["severity"] == "critical" and f["value"] > 4.5 and f["constraint"] == "no_raise"
    assert "ISO 10816" in f["basis"]


def test_drifting_humidity_sensor_is_caught_by_the_crah_reference(tel):
    found = codes(diag(tel, "2026-05-01 12:00"))
    assert found[("ENV-CA-2", "SENSOR_DRIFT")]["severity"] in ("warning", "critical")
    assert ("ENV-CA-2", "ROOM_HUMIDITY") not in found                                # a drifting sensor says nothing about the room
    assert ("ENV-CA-1", "SENSOR_DRIFT") not in found


def test_comm_loss_on_a_cooling_device_blocks_running_warmer(tel):
    d = diag(tel, "2026-04-26 15:00")
    assert codes(d)[("CT-1", "COMM_LOSS")]["constraint"] == "no_raise" and d["devices_answering"] == 21


@pytest.mark.parametrize("device, code, constraint", [
    ("CRAH-1", "CRAH_TRIPPED", "fallback"), ("CH-1", "CHILLER_TRIPPED", "fallback"),
    ("CT-1", "COOLING_TOWER_TRIPPED", "fallback"), ("CHWP-1", "RUNNING_ON_STANDBY", "no_raise"),
])
def test_trips(tel, device, code, constraint):
    d = diag(tel, "2026-04-21 00:30", trips=(device,))
    assert codes(d)[(device, code)]["constraint"] == constraint and d["constraint"] == constraint


def test_equipment_window_never_sees_the_future(tel):
    win = EquipmentWindow(tel, pd.Timestamp("2026-04-21 00:30"))
    assert win.frame.index.max() == pd.Timestamp("2026-04-21 00:30")
    assert win.frame.index.min() >= pd.Timestamp("2026-04-14 00:30")


# ---- rule R5 -----------------------------------------------------------------------------------
def test_safety_rule_r5():
    safety = SafetyFilter(fallback_sp=20)
    reading = {c: 24.0 for c in C.INLET_COLS}
    assert safety.check(22, 21, reading, equipment="no_raise") == (21.0, ["R5_equipment_constraint"])
    assert safety.check(20, 21, reading, equipment="no_raise") == (20.0, [])          # cooling more is always allowed
    sp, fired = safety.check(22, 22, reading, equipment="fallback")
    assert sp == 21 and fired[0] == "R5_equipment_constraint"                          # toward fallback, 1 °C per step
    assert safety.check(19, 19, reading, equipment="fallback")[0] == 19               # never warmer while a unit is down
    with pytest.raises(ValueError):
        safety.check(22, 21, reading, equipment="ignore")


# ---- the Hardware Engineer in a case -----------------------------------------------------------
def test_hardware_warning_stops_the_ai_running_warmer(ctx):
    result = run_case(CaseRequest(at="2026-04-29 05:30"), ctx)
    assert result.status == "completed" and all(c.passed for c in result.checks), result.checks
    assert result.evidence["equipment"]["constraint"] == "no_raise"
    assert "R5_equipment_constraint" in result.evidence["safety"]["rules_fired"]
    assert result.plan[0] > result.setpoint_in_use >= result.recommended_setpoint     # MPC wanted warmer; R5 said no
    assert "hardware_engineer" in result.agent_notes and "BEARING_WEAR" in result.explanation


def test_tripped_crah_sends_the_room_toward_fallback(ctx):
    result = run_case(CaseRequest(at="2026-04-21 00:30", equipment_fault=("CRAH-1",)), ctx)
    assert result.status == "completed" and result.evidence["equipment"]["constraint"] == "fallback"
    assert result.recommended_setpoint <= min(result.setpoint_in_use, 21.0)
    assert any(c.name.startswith("Hardware constraint respected") and c.passed for c in result.checks)


def test_g1_rejects_unknown_equipment_faults():
    with pytest.raises(ValidationError):
        CaseRequest(at="2026-04-21 00:30", equipment_fault=("PDU-B6",))               # not a trippable cooling device


def test_g3_rejects_hardware_evidence_that_does_not_match_a_fresh_poll(ctx, monkeypatch):
    from predictive_cooling.agents import tools as T
    real = T.diagnose_equipment
    calls = {"n": 0}

    def stale_then_real(win):                         # the agent's copy says "all fine"; G3's own re-poll does not
        calls["n"] += 1
        out = real(win)
        if calls["n"] == 1:
            out = {**out, "overall": "ok", "constraint": "none", "findings": []}
        return out
    monkeypatch.setattr(T, "diagnose_equipment", stale_then_real)
    result = run_case(CaseRequest(at="2026-04-29 05:30"), ctx)
    assert result.status == "failed" and result.reason_codes == ["EQUIPMENT_EVIDENCE_MISMATCH"]
    assert result.recommended_setpoint is None and calls["n"] == 2
