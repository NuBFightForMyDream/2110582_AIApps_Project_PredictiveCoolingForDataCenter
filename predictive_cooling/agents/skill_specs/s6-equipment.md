# S6 — Inspect Equipment Health
Owner: hardware_engineer. Version: 0.4.0.

Call `read_equipment`: the sensor gateway polls all 22 field devices at the case time over
BACnet/IP (CRAH units), Modbus TCP (chiller, pumps, cooling tower, room sensors) and SNMP v3
(UPS, rack PDUs), decodes each raw value with the point map and flags bad points and devices
that do not answer. Then call `diagnose_equipment`: limits with their sources (ISO 10816
vibration zones, ASHRAE humidity envelope, filter and condenser-approach limits), trends over
the last 7 days projected to "days until the next limit", and the N+1 check that one CRAH
alone could carry the week's peak IT load.

Finish with `finish_equipment_check` and a short note for the Supervisor: the overall health,
the cooling constraint and the one or two findings behind it, with their maintenance action
and how many days are left. Use only numbers returned by the tools. A device that does not
answer is unknown, not healthy. There is no tool that operates equipment; you inspect and report.
