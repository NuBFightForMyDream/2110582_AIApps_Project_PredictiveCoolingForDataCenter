# Overview

[Architecture index](README.md)

**Question the system answers:** *if the load will rise in 30 minutes, how should the cooling change now so every rack stays
at or below 27 °C while using as little electricity as possible?*

**Scope.** One mock 12-rack server room (two rows, one shared cold aisle, two CRAH units, a chiller, pumps, a cooling tower,
a UPS and 12 rack PDUs), 13 weeks of 15-minute data (2 Feb – 3 May 2026). One control knob: the CRAH supply-air setpoint
(16–24 °C). Everything is simulated by `plant.py`; nothing is sent to real equipment.

## Two layers, one set of tools

| Layer | Runs | Decides | Scored by |
|---|---|---|---|
| Control layer | every 15 minutes, closed loop | the setpoint (forecast → 81-plan MPC → safety rules R1–R6) | the simulated plant, two unseen test weeks |
| Agent layer | on an operator's question | what to check, in which order, and how to explain it | G3 recomputes every number before release |

The agents never compute numbers. They call the same Python functions the control layer uses (as tools), and four guards
check every request, tool call and answer. The hardware layer (rule R5) and the security layer (rule R6) feed both layers.

## What is real and what is simulated

| Real (could run on a site) | Simulated here |
|---|---|
| Cleaning rules, forecaster, MPC, safety rules, agents and guards | The room (`plant.py`), its 13-week history and the operator who ran it |
| Sensor gateway decoding (BACnet REAL, Modbus registers × scale, SNMP integers) | The devices behind the gateway (`SimulatedFieldBus` plays the historian) |
| Diagnostics, integrity model, replay check, command audit, signing | Hardware faults and cyber attacks (injected on purpose) |
| Upgrade economics (kWh → THB, tCO₂, payback) | The effect of each upgrade (a plant-model change, measured in closed loop) |

A real deployment would replace `SimulatedFieldBus` with a BACnet/Modbus/SNMP client behind the same `read()` method and
retrain the forecaster and the integrity model on the site's own history.
