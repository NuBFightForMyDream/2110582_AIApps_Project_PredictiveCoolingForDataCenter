# Data

[Architecture index](README.md)

## Sensor log — `data/sensor_history.csv`

What a BMS/DCIM exports every 15 minutes: 8,718 rows × 25 columns (outdoor temperature, IT load and power, 12 rack inlets,
supply/return air, setpoint, CRAH fan speed, chiller / CRAH fan / pumps + tower / cooling / facility power, PUE). Built by
`dataset.py` from `plant.py`:

- **Workload**: office-hours demand, a weekday GPU training batch 01:00–05:00 on racks B4–B6, an afternoon reporting job,
  random unplanned jobs.
- **Weather**: hot humid climate, daily cycle, warming toward April, afternoon storms.
- **Operator**: a deadband rule plus occasional setpoint step tests, so the history covers many setpoints.
- **Log faults on purpose**: 0.3 % missing cells, 85 / −40 / 0 °C glitches, inlet A3 stuck for 8 h, two logger outages (18 rows).

## Equipment historian — `data/equipment_telemetry.csv`

What the 22 field devices report: 8,736 rows × 69 points (`hardware/telemetry.py`), from the same plant run (same seeds),
so temperatures and power agree with the sensor log. Adds chilled- and condenser-water temperatures, pump flow and
vibration, filter ΔP, airflow, humidity, containment pressure, UPS and per-rack PDU power. Hardware faults injected in the
test weeks: CRAH-2 filter loading (15 Apr), CH-1 condenser fouling (23 Apr), CHWP-1 bearing wear (24 Apr), ENV-CA-2
humidity drift (22 Apr), CT-1 comm loss (26 Apr 14:00–16:00). See [hardware.md](hardware.md).

## Cleaning and the split — `preprocess.py`

1. Put every reading back on the 15-minute grid. 2. Values outside the physical range become missing. 3. A sensor repeating
the exact value 6+ times is stuck → missing. 4. Holes up to 1 hour are interpolated; longer ones stay missing.

Chronological split, never shuffled: train weeks 1–9 (to 6 Apr), validation weeks 10–11 (tune baselines, safety margins,
integrity thresholds), test weeks 12–13 (20 Apr – 3 May, every reported result).

## No look-ahead

Agent tools see only readings at or before the case time: 2 hours of the sensor log (`CaseWindow`), 26 hours for the replay
check, 7 days of the equipment historian (`EquipmentWindow`). The setpoint decided *at* the case time is hidden.
All generators use fixed seeds: `python -m predictive_cooling.dataset` and `python -m predictive_cooling.hardware`
reproduce the files exactly.
