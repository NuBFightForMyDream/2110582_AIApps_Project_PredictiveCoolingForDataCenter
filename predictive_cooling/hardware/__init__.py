"""Hardware layer: the field devices, the sensor gateway that reads them, their historian and diagnostics.

    registry.py     every device and its point list (protocol, address, encoding, scale, valid range)
    gateway.py      polls a device: raw value on the wire -> engineering units + quality flag
    telemetry.py    data/equipment_telemetry.csv, the equipment historian (with injected hardware faults)
    diagnostics.py  limits (ISO 10816, ASHRAE), trends -> days until a limit, N+1 cooling capacity

The Hardware Engineer agent (skill S6) reads the hardware through these modules and reports to the Supervisor.
"""
from .gateway import CommError, Gateway, SimulatedFieldBus
from .registry import DEVICES, REGISTRY, TRIPPABLE

__all__ = ["CommError", "DEVICES", "Gateway", "REGISTRY", "SimulatedFieldBus", "TRIPPABLE"]
