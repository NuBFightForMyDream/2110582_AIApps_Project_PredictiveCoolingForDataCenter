"""Every field device in the mock room and its point list (what the sensor gateway polls).

A real data center exposes its equipment over three building protocols:
* BACnet/IP   — CRAH units (native BACnet controllers; analog values are IEEE floats)
* Modbus TCP  — chiller, pump drives, cooling tower, room sensors (16-bit registers with a fixed scale)
* SNMP v3     — UPS (RFC 1628 UPS-MIB) and rack PDUs (vendor PDU MIB)

A point is one value on one device: its protocol address, how the raw value is encoded, the scale that
turns the raw value into engineering units, and the physically possible range (outside it the gateway
marks the value as bad instead of trusting it). Modbus register numbers and IP endpoints are this site's
point map, not vendor defaults.
"""
from dataclasses import dataclass

from .. import config as C


@dataclass(frozen=True)
class Point:
    name: str
    unit: str
    address: str
    encoding: str = "int16"          # int16 / uint16 (Modbus), real (BACnet float32), gauge32 (SNMP integer)
    scale: float = 0.1               # engineering value = raw x scale (ignored for "real")
    valid: tuple = (-1e9, 1e9)       # physically possible range


@dataclass(frozen=True)
class Device:
    id: str
    kind: str                        # crah, chiller, pump, cooling_tower, ups, env, pdu
    name: str
    location: str
    protocol: str
    endpoint: str
    points: tuple
    cooling_path: bool = False       # a fault here can reduce cooling capacity
    group: str | None = None         # redundancy group (units that back each other up)
    standby: bool = False            # normally off; starts when the duty unit trips

    def column(self, point: str) -> str:
        return f"{self.id}.{point}"

    @property
    def columns(self):
        return [self.column(p.name) for p in self.points]

    def point(self, name: str) -> Point:
        return next(p for p in self.points if p.name == name)


def _crah(n):
    pts = (
        Point("status", "", "BI:1", "real", valid=(0, 1)),
        Point("setpoint_c", "°C", "AV:1", "real", valid=(10, 30)),
        Point("supply_air_c", "°C", "AI:1", "real", valid=(5, 40)),
        Point("return_air_c", "°C", "AI:2", "real", valid=(5, 60)),
        Point("return_rh_pct", "%RH", "AI:3", "real", valid=(0, 100)),
        Point("fan_speed_pct", "%", "AI:4", "real", valid=(0, 100)),
        Point("fan_kw", "kW", "AI:5", "real", valid=(0, 50)),
        Point("airflow_m3h", "m³/h", "AI:6", "real", valid=(0, 60000)),
        Point("filter_dp_pa", "Pa", "AI:7", "real", valid=(0, 1000)),
        Point("chw_valve_pct", "%", "AI:8", "real", valid=(0, 100)),
    )
    return Device(f"CRAH-{n}", "crah", f"Computer-room air handler {n}", "Left wall", "BACnet/IP",
                  f"10.20.1.1{n}:47808 · device {1000 + n}", pts, cooling_path=True, group="crah")


def _pump(n, standby):
    pts = (
        Point("status", "", "HR 40001", "uint16", 1, (0, 1)),
        Point("speed_hz", "Hz", "HR 40002", "uint16", 0.1, (0, 60)),
        Point("flow_m3h", "m³/h", "HR 40003", "uint16", 0.1, (0, 100)),
        Point("kw", "kW", "HR 40004", "uint16", 0.01, (0, 30)),
        Point("vibration_mm_s", "mm/s", "HR 40005", "uint16", 0.01, (0, 50)),
        Point("bearing_temp_c", "°C", "HR 40006", "int16", 0.1, (-10, 150)),
    )
    role = "standby" if standby else "duty"
    return Device(f"CHWP-{n}", "pump", f"Chilled-water pump {n} ({role})", "Plant room", "Modbus TCP",
                  f"10.20.1.31:502 · unit {n}", pts, cooling_path=True, group="chwp", standby=standby)


def _pdu(rack):
    pts = (Point("power_kw", "kW", "vendor PDU MIB · total active power (W)", "gauge32", 0.001, (0, 40)),)
    row = "Row A" if rack.startswith("A") else "Row B"
    return Device(f"PDU-{rack}", "pdu", f"Rack PDU {rack} ({C.RACK_ROLE[rack]})", f"{row}, rack {rack}", "SNMP v3",
                  f"10.20.4.{10 + C.RACKS.index(rack)}:161", pts)


DEVICES = [
    _crah(1),
    _crah(2),
    Device("CH-1", "chiller", "Water-cooled chiller", "Plant room", "Modbus TCP", "10.20.1.21:502 · unit 1", (
        Point("status", "", "HR 40001", "uint16", 1, (0, 1)),
        Point("load_pct", "%", "HR 40002", "uint16", 0.1, (0, 120)),
        Point("kw", "kW", "HR 40003", "uint16", 0.1, (0, 300)),
        Point("cop", "", "HR 40004", "uint16", 0.01, (0, 15)),
        Point("chws_c", "°C", "HR 40005", "int16", 0.1, (0, 25)),
        Point("chwr_c", "°C", "HR 40006", "int16", 0.1, (0, 30)),
        Point("cond_in_c", "°C", "HR 40007", "int16", 0.1, (5, 50)),
        Point("cond_out_c", "°C", "HR 40008", "int16", 0.1, (5, 55)),
        Point("cond_approach_c", "°C", "HR 40009", "int16", 0.01, (-2, 15)),
    ), cooling_path=True, group="chiller"),
    _pump(1, standby=False),
    _pump(2, standby=True),
    Device("CT-1", "cooling_tower", "Cooling tower + condenser pump", "Roof", "Modbus TCP", "10.20.1.41:502 · unit 1", (
        Point("status", "", "HR 40001", "uint16", 1, (0, 1)),
        Point("fan_speed_pct", "%", "HR 40002", "uint16", 0.1, (0, 100)),
        Point("kw", "kW", "HR 40003", "uint16", 0.01, (0, 50)),
        Point("wet_bulb_c", "°C", "HR 40004", "int16", 0.1, (-10, 40)),
        Point("cold_water_c", "°C", "HR 40005", "int16", 0.1, (5, 45)),
        Point("approach_c", "°C", "HR 40006", "int16", 0.01, (0, 20)),
    ), cooling_path=True, group="tower"),
    Device("UPS-1", "ups", "Double-conversion UPS", "Electrical room", "SNMP v3", "10.20.2.11:161 · UPS-MIB (RFC 1628)", (
        Point("output_source", "", "1.3.6.1.2.1.33.1.4.1.0 upsOutputSource", "gauge32", 1, (1, 7)),
        Point("load_pct", "%", "1.3.6.1.2.1.33.1.4.4.1.5.1 upsOutputPercentLoad", "gauge32", 1, (0, 150)),
        Point("output_kw", "kW", "1.3.6.1.2.1.33.1.4.4.1.4.1 upsOutputPower (W)", "gauge32", 0.001, (0, 300)),
        Point("battery_temp_c", "°C", "1.3.6.1.2.1.33.1.2.7.0 upsBatteryTemperature", "gauge32", 1, (0, 80)),
        Point("efficiency_pct", "%", "vendor UPS MIB · efficiency", "gauge32", 0.1, (0, 100)),
    )),
    Device("ENV-CA-1", "env", "Cold-aisle temperature/humidity sensor (row A side)", "Cold aisle, row A", "Modbus TCP",
           "10.20.3.11:502 · unit 1", (Point("temp_c", "°C", "IR 30001", "int16", 0.1, (-20, 60)),
                                       Point("rh_pct", "%RH", "IR 30002", "uint16", 0.1, (0, 100)))),
    Device("ENV-CA-2", "env", "Cold-aisle temperature/humidity sensor (row B side)", "Cold aisle, row B", "Modbus TCP",
           "10.20.3.11:502 · unit 2", (Point("temp_c", "°C", "IR 30001", "int16", 0.1, (-20, 60)),
                                       Point("rh_pct", "%RH", "IR 30002", "uint16", 0.1, (0, 100)))),
    Device("ENV-DP-1", "env", "Containment differential-pressure sensor (cold vs hot aisle)", "Cold-aisle door",
           "Modbus TCP", "10.20.3.11:502 · unit 3", (Point("aisle_dp_pa", "Pa", "IR 30001", "int16", 0.01, (-50, 50)),),
           cooling_path=True),
    *[_pdu(r) for r in C.RACKS],
]
REGISTRY = {d.id: d for d in DEVICES}
COLUMNS = [col for d in DEVICES for col in d.columns]

# Devices the demo can "trip" (status -> 0 for the last 30 minutes before a case).
TRIPPABLE = ("CRAH-1", "CRAH-2", "CH-1", "CHWP-1", "CT-1")

# Nameplate figures used by the telemetry model and the capacity check.
CRAH_RATED_KW = 140.0                # sensible cooling per CRAH at full airflow
CRAH_RATED_AIRFLOW_M3H = 34000.0     # per CRAH at 100 % fan speed, clean filter
CHILLER_RATED_KW = 250.0
UPS_RATED_KW = 180.0                 # 200 kVA at power factor 0.9
CHW_DESIGN_FLOW_M3H = 24.0
