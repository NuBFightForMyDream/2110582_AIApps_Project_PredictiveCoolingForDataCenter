"""Sensor gateway: poll each device, decode raw values with the point map, flag what cannot be trusted.

    field device --(BACnet/IP | Modbus TCP | SNMP v3)--> raw value --(point map)--> engineering value + quality

A backend answers `read(device, at)` with the device's raw values, or raises CommError when the device does
not answer. `SimulatedFieldBus` plays the devices from the equipment historian (data/equipment_telemetry.csv)
and encodes each value the way that protocol would carry it, so the gateway does the same decoding work it
would do against real equipment. A real site plugs in a backend built on a BACnet, Modbus or SNMP client with
the same `read` method; nothing above the gateway changes.

Quality flags per point:
    good          decoded and inside the physically possible range
    out_of_range  decoded but impossible (bad wiring, failed transmitter, register overflow) -> value dropped
    no_data       the device answered but this point was empty
    comm_loss     the device did not answer at all
"""
import math

import numpy as np
import pandas as pd

from .registry import REGISTRY, Device

LIMITS = {"int16": (-32768, 32767), "uint16": (0, 65535), "gauge32": (0, 2 ** 32 - 1)}


class CommError(Exception):
    """The device did not answer the poll (timeout / connection refused)."""


def encode(point, value):
    """Engineering value -> the raw value the device would put on the wire (None = empty)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if point.encoding == "real":
        return float(np.float32(value))
    low, high = LIMITS[point.encoding]
    return int(min(max(round(value / point.scale), low), high))      # registers saturate at their limits


def decode(point, raw):
    """Raw value -> (engineering value or None, quality flag)."""
    if raw is None:
        return None, "no_data"
    value = float(raw) if point.encoding == "real" else raw * point.scale
    if point.encoding != "real":
        low, high = LIMITS[point.encoding]
        if raw == high or (point.encoding == "int16" and raw == low):
            return None, "out_of_range"                                # saturated register (0 is a real reading)
    low, high = point.valid
    if not low <= value <= high:
        return None, "out_of_range"
    return round(value, 6), "good"


class SimulatedFieldBus:
    """Plays every device from the historian: one row per 15-minute poll."""

    def __init__(self, telemetry: pd.DataFrame):
        self.telemetry = telemetry

    def read(self, device: Device, at) -> dict:
        at = pd.Timestamp(at)
        if at not in self.telemetry.index:
            raise CommError(f"{device.id}: no answer at {at:%H:%M}")
        row = self.telemetry.loc[at, device.columns]
        if row.isna().all():
            raise CommError(f"{device.id}: timeout ({device.protocol} {device.endpoint})")
        return {p.name: encode(p, row[device.column(p.name)]) for p in device.points}


class Gateway:
    def __init__(self, backend):
        self.backend = backend

    def poll(self, device_id: str, at) -> dict:
        device = REGISTRY[device_id]
        try:
            raw = self.backend.read(device, at)
        except CommError as exc:
            return {"device": device_id, "comm": "comm_loss", "error": str(exc), "raw": {}, "values": {},
                    "quality": {p.name: "comm_loss" for p in device.points}}
        values, quality = {}, {}
        for p in device.points:
            values[p.name], quality[p.name] = decode(p, raw.get(p.name))
        return {"device": device_id, "comm": "ok", "error": "", "raw": raw, "values": values, "quality": quality}

    def poll_all(self, at, device_ids=None) -> dict:
        return {d: self.poll(d, at) for d in (device_ids or REGISTRY)}

    def point_table(self, device_id: str, at) -> pd.DataFrame:
        return point_table(self.poll(device_id, at))


def point_table(reading: dict) -> pd.DataFrame:
    """One row per point of a poll: protocol address, raw value on the wire, decoded value and quality (for the UI)."""
    device = REGISTRY[reading["device"]]
    return pd.DataFrame([{
        "Point": p.name, "Address": p.address, "Encoding": p.encoding,
        "Scale": "—" if p.encoding == "real" else f"× {p.scale:g}",
        "Raw value": None if reading["raw"].get(p.name) is None else str(reading["raw"][p.name]),
        "Value": reading["values"].get(p.name), "Unit": p.unit, "Quality": reading["quality"][p.name]} for p in device.points])
