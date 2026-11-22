# Predictive Cooling Optimization for Data Centers
![CoverPage](https://github.com/NuBFightForMyDream/2110582_AIApps_Project_PredictiveCoolingForDataCenter/blob/main/CoverPage.png)

> **"If the load will rise in 30 minutes, how should we adjust the cooling right now so the racks stay below the limit and we use as little electricity as possible?"**

An **agent-based** system: five agents (Supervisor, Data Analyst, Security Analyst, Hardware Engineer, Cooling Advisor) answer
an operator's question about the room by calling guarded Python tools. The tools are the proposal's pipeline: sensor data → cleaning → ML
forecast → 81-plan MPC → safety filter, with a simulated room (plant) as the judge, plus a **hardware layer**: a sensor gateway
that polls 22 field devices over BACnet/IP, Modbus TCP and SNMP v3, and diagnostics that tell the agents when the equipment
itself (filters, pumps, chiller, sensors) is going wrong, and a **security layer**: an ML integrity model and replay detection
that catch forged sensor data, a prompt-injection screen, signed recommendations and a hash-chained audit trail. The original agent architecture is kept: LangGraph, skills S1–S5,
guardrails G1/G2/G3, and offline or Gemini mode. What changed is what the agents work with. They now read **sensor data from the
data center**, use a **forecaster trained on a mock sensor dataset**, and choose a setpoint with **MPC**. Infrastructure that was
not needed for the idea (FastAPI, Supabase/auth, SustainDC install, CSV import) is removed.

## The idea in 30 seconds

| The problem | The idea | The result |
|---|---|---|
| Server rooms run their cooling at a safe but cold setpoint all day. Colder than needed = wasted electricity. | Every 15 minutes: **forecast the next hour**, try **81 setpoint plans**, keep only the ones that stay below 27 °C, and pick the cheapest. | **2.1 % less cooling energy** than a tuned rule-based controller (5.0 % vs a fixed setpoint), **0 minutes** above 27 °C. |

```mermaid
flowchart LR
    S["① Sensors<br/>12 rack inlets, power,<br/>weather · every 15 min"]:::step --> CL["② Clean<br/>gaps, glitches,<br/>stuck sensors"]:::step
    CL --> F["③ Forecast (ML)<br/>next 60 min for<br/>any setpoint plan"]:::ai
    F --> M["④ MPC<br/>try 81 plans → keep safe<br/>→ pick cheapest"]:::ai
    M --> SF["⑤ Safety filter<br/>4 rules check<br/>every command"]:::guard
    SF --> P["⑥ Room<br/>apply the setpoint,<br/>repeat in 15 min ↺"]:::ok
    classDef step fill:#ffffff,stroke:#c3c2b7,color:#0b0b0b
    classDef ai fill:#e8f1fc,stroke:#2a78d6,color:#0b0b0b,stroke-width:2px
    classDef guard fill:#fbeeee,stroke:#d03b3b,color:#0b0b0b
    classDef ok fill:#e6f6ef,stroke:#1baf7a,color:#0b0b0b
```

Blue = machine learning, red = safety, green = what reaches the room.

![architecture](docs/pipeline.png)

## Two layers

```mermaid
flowchart TD
    Q["Operator question + moment"] --> G1["G1 · prompt-injection screen, typed request, case time, scope, budgets"]
    G1 --> SUP["Supervisor · S1 Plan"]
    SUP -->|"G2: call_data_analyst"| DA["Data Analyst · S2 Inspect, S3 Analyze & Forecast"]
    DA -->|"ready?"| SUP
    SUP -->|"G2: call_security_analyst"| SA["Security Analyst · S7 Verify data integrity"]
    SA -->|"trusted / untrusted (R6)"| SUP
    SUP -->|"G2: call_hardware_engineer"| HE["Hardware Engineer · S6 Inspect equipment"]
    HE -->|"findings + cooling constraint"| SUP
    SUP -->|"G2: call_cooling_advisor (recommend + data ready + trusted)"| CA["Cooling Advisor · S4 Evaluate plans (R5 applies the constraint)"]
    CA -->|"proposed setpoint"| SUP
    SUP --> G3["G3 · re-read sensors, re-check integrity, re-poll hardware, recompute forecast + MPC + safety, reject mismatch"]
    G3 --> S5["Supervisor · S5 Compose verified answer (no actuation)"]
    S5 --> G4["G4 · redact model notes, HMAC-sign the recommendation, seal the hash-chained trace"]
    SA -.->|"tools"| T4["check_sensor_integrity · audit_command_channel"]
    DA -.->|"tools"| T1["① read_sensors · ② inspect_data_quality · ③ summarize_state, forecast_hold"]
    HE -.->|"tools"| T3["read_equipment (sensor gateway) · diagnose_equipment"]
    CA -.->|"tools"| T2["④ run_mpc · ⑤ check_safety · propose_setpoint"]
```

- **Agent layer (on demand)**: decides *what to check, in which order*, and explains. It cannot compute numbers itself, change
  the 27 °C limit, call tools outside its skill, or touch equipment.
- **Tool / control layer (every 15 min)**: the same Python steps also run the closed-loop controller that is scored on the plant.

| Role | Skills | Tools (allowlist enforced by G2) |
|---|---|---|
| Supervisor (parent) | S1 Plan, S5 Compose | `call_data_analyst`, `call_security_analyst`, `call_hardware_engineer`, `call_cooling_advisor`, `finish_case` |
| Data Analyst (child) | S2 Inspect, S3 Analyze & Forecast | `read_sensors`, `inspect_data_quality`, `summarize_state`, `forecast_hold`, `finish_analysis` |
| Security Analyst (child) | S7 Verify data integrity | `check_sensor_integrity`, `audit_command_channel`, `finish_security_review` |
| Hardware Engineer (child) | S6 Inspect equipment health | `read_equipment`, `diagnose_equipment`, `finish_equipment_check` |
| Cooling Advisor (child) | S4 Evaluate plans | `run_mpc`, `check_safety`, `propose_setpoint` |

| Guard | Where | Checks | Stops with |
|---|---|---|---|
| G1 | Before the graph | **Prompt-injection screen** of the question (blocked / flagged / clean), Pydantic request (15-min grid, known racks and devices, question length), case time inside the logs, budgets | `security_alert` (`PROMPT_INJECTION_BLOCKED`), `failed` |
| G2 | Every tool call and delegation | Skill owner + tool allowlist, phase (e.g. no MPC before inspection, no Cooling Advisor before the Hardware Engineer), shared tool/model budget, deadline. Tools only see readings **at or before** the case time (2 h of sensors, 7 days of equipment data) | `TOOL_NOT_ALLOWED`, `budget_exceeded` |
| G3 | After the agents, before release | Re-reads the sensors, re-inspects quality, **re-runs the integrity checks**, **re-polls every device and re-runs the hardware diagnosis**, recomputes state, forecast, MPC and safety filter; proposal must equal the recomputed setpoint; range/rate limit; hardware constraint respected; plan safe | `security_alert` (→ R6), `insufficient_data` (→ R1 fallback), `PROPOSAL_EVIDENCE_MISMATCH`, `EQUIPMENT_EVIDENCE_MISMATCH`, `SECURITY_EVIDENCE_MISMATCH` |
| G4 | After S5, on release | Redacts keys, links and e-mails from model notes and flags claims that equipment was changed; HMAC-signs the recommendation (15-min expiry, one-time nonce); seals the trace in a SHA-256 hash chain | – |

**Modes.** *Offline*: LangGraph runs fixed role procedures, no LLM, deterministic. *Gemini*: real parent/child function
calling (separate histories, one tool per turn, phase-limited tool lists, shared budgets). Set `GEMINI_API_KEY` (and optionally
`GEMINI_MODEL`) to use it. Without a key the case fails closed. Live run before the Hardware Engineer was added (5 Nov 2026,
`gemini-3.5-flash-lite`, case 21 Apr 00:30): 11 model calls, 36.8 s, G3 6/6 passed, same answer as offline (21 °C, plan
21 → 21 → 21 → 22). With five agents a case now needs **19 model calls**; this was tested with scripted providers and a
mock Claude server, not yet live. Live modes are rate limited to 5 cases per 10 minutes per session and 40 per hour per app. Gemini cases get a 300 s deadline and retry 429/5xx errors. On a free key, prefer a flash-lite model: the bigger
flash models allow only ~20 requests per day, and `gemini-flash-latest` often answers 503 "high demand". The loops are also tested with a scripted provider, including a forged proposal that G3 must reject.
*Claude*: the same loops on Claude Haiku 5.5, enabled by `ANTHROPIC_API_KEY` and billed per token. Each turn forces one
tool call, and refusals or cut-off answers fail closed. Tested through the SDK against a mock server.

```mermaid
sequenceDiagram
    participant O as Operator
    participant S as Supervisor
    participant D as Data Analyst
    participant A as Security Analyst
    participant H as Hardware Engineer
    participant C as Cooling Advisor
    participant G as G3 verify
    O->>S: question + moment (checked by G1)
    S->>D: inspect sensors, forecast next hour
    D-->>S: data OK? hold-setpoint forecast
    S->>A: are the readings genuine?
    A-->>S: trusted / untrusted
    S->>H: poll the equipment, check health
    H-->>S: findings + cooling constraint
    S->>C: find the best safe setpoint
    C-->>S: proposal (81-plan MPC + safety, R5)
    S->>G: re-read sensors, re-check integrity, re-poll hardware, recompute all
    G-->>O: verified, signed answer (or fallback)
```

![agent trace](docs/agents-trace.png)

Example case (`python -m predictive_cooling.agents --at "2026-04-21 00:30"`): the Data Analyst finds that holding 22 °C would
reach 27.5 °C (incl. margin) when the 01:00 GPU batch starts. The Cooling Advisor finds 18 of 81 plans safe and proposes
21 °C (plan 21 → 21 → 21 → 22). The Security Analyst finds the readings consistent with physics, and the Hardware Engineer finds all
22 devices healthy. G3 re-reads and recomputes, all 9 checks pass, G4 signs the answer, and it is "Change from 22 °C to 21 °C now". With `--fault B5 B6`, the data is not ready, the AI is withheld, and
safety rule R1 moves toward the 20 °C fallback. At `--at "2026-04-29 05:30"` the MPC wants to warm the room after the GPU batch
(21 °C), but the Hardware Engineer reports lost N+1 capacity (clogging CRAH-2 filter) and a worn pump bearing, so rule R5 keeps
20 °C. With `--attack spoofing` at 21 Apr 02:00 the Security Analyst sees B4–B6 reading ~2.9 °C cooler than their PDU power allows:
status `security_alert`, the AI is withheld and R6 keeps the room no warmer than now.

## Mock dataset: `data/sensor_history.csv`

A simulated 12-rack server room (two rows facing one shared cold aisle, CRAH units on the left wall), 2 Feb – 3 May 2026,
one reading every 15 minutes: **8,718 rows × 25 sensors** (about 1.6 MB, opens in Excel).

![floor map](docs/floor-map.png)

| Column | Unit | Meaning |
|---|---|---|
| `outdoor_temp_c` | °C | Outdoor air temperature (hot, humid Bangkok-like climate, warming toward April, afternoon storms) |
| `it_load_pct`, `it_power_kw` | %, kW | Average CPU/GPU load and server power (including the fans inside the servers) |
| `inlet_A1_c` … `inlet_B6_c` | °C | Air temperature at the front of each rack: **must stay at or below 27 °C** (ASHRAE) |
| `supply_air_c`, `return_air_c` | °C | Cold air leaving the CRAH units / hot air coming back |
| `crah_setpoint_c` | °C | **The one knob the AI controls**: supply-air setpoint (16–24 °C) |
| `crah_fan_pct` | % | CRAH fan speed (automatic, follows load) |
| `chiller_kw`, `crah_fan_kw`, `pump_tower_kw`, `cooling_kw` | kW | Cooling sub-meters |
| `facility_kw`, `pue` | kW, – | Whole-building power and PUE = facility ÷ IT |

How the data is made (`predictive_cooling/dataset.py`):

- **Workload**: office-hour demand, a **GPU training batch every weekday night 01:00–05:00** (racks B4–B6), an afternoon reporting job, and random unplanned jobs.
- **Plant**: `plant.py` is a simple physics model. Hot air recirculates (B6 at the end of the row is the hottest), the room has a thermal lag of about 25 minutes,
  the chiller COP improves by about 4 % per °C of higher setpoint, and server fans speed up when the inlet goes above 26 °C (so IT power rises).
- **Previous operator**: a simple rule ran the room and **occasionally ran setpoint step tests**, so the history contains many setpoint levels.
  (If the setpoint never changed, the model could not learn what the setpoint does.)
- **Real-world problems added on purpose**: 0.3 % missing values, glitch readings of 85/−40/0 °C, sensor A3 stuck for 8 hours, and 2 logger outages (18 rows).

Regenerate it with `python -m predictive_cooling.dataset` (seeds are fixed, so the result is identical every time).

Cleaning and the time-based split (never shuffle a time series: the model is scored on weeks it never saw):

```mermaid
flowchart LR
    R["Raw log"]:::step --> A["1 · back on the<br/>15-min grid"]:::step --> B["2 · impossible<br/>values → missing"]:::guard
    B --> S["3 · stuck sensor<br/>(6+ repeats) → missing"]:::guard --> F["4 · fill holes<br/>≤ 1 hour"]:::step
    F --> T["Train<br/>weeks 1–9"]:::ai
    F --> V["Validate<br/>weeks 10–11"]:::step
    F --> X["Test<br/>weeks 12–13"]:::ok
    classDef step fill:#ffffff,stroke:#c3c2b7,color:#0b0b0b
    classDef ai fill:#e8f1fc,stroke:#2a78d6,color:#0b0b0b,stroke-width:2px
    classDef guard fill:#fbeeee,stroke:#d03b3b,color:#0b0b0b
    classDef ok fill:#e6f6ef,stroke:#1baf7a,color:#0b0b0b
```

## Hardware layer: `predictive_cooling/hardware/`

The room log above is what a BMS summary shows. The **equipment historian** `data/equipment_telemetry.csv` is what the
devices themselves report: **69 points from 22 devices** every 15 minutes (8,736 rows), derived from the same plant run
(same seeds, so temperatures and power agree with the room log). Rebuild it with `python -m predictive_cooling.hardware`.

| Device | Protocol | Points (examples) |
|---|---|---|
| CRAH-1, CRAH-2 | BACnet/IP (REAL values) | status, setpoint, supply/return air, return RH, fan speed/kW, airflow, filter ΔP, chilled-water valve |
| CH-1 chiller | Modbus TCP (16-bit registers × scale) | load, kW, COP, chilled-water supply/return, condenser in/out, condenser approach |
| CHWP-1 (duty), CHWP-2 (standby) | Modbus TCP via the drive | status, speed, flow, kW, vibration (mm/s RMS), bearing temperature |
| CT-1 cooling tower | Modbus TCP | fan speed, kW, wet bulb, cold-water temperature, approach |
| UPS-1 | SNMP v3, RFC 1628 UPS-MIB | output source, load %, output kW, battery temperature, efficiency |
| ENV-CA-1/2, ENV-DP-1 | Modbus TCP | cold-aisle temperature + RH (row A / row B side), containment over-pressure |
| PDU-A1 … PDU-B6 | SNMP v3 | power per rack |

```mermaid
flowchart LR
    D["22 field devices"]:::step --> P["BACnet/IP · Modbus TCP · SNMP v3"]:::step
    P --> GW["Sensor gateway<br/>raw → engineering units<br/>+ quality flag"]:::guard
    GW --> DX["Diagnostics<br/>limits · 7-day trends · N+1"]:::ai
    DX --> HE["Hardware Engineer (S6)"]:::agent
    HE --> SUP["Supervisor"]:::agent
    HE -.->|"cooling constraint"| R5["Safety rule R5"]:::guard
    classDef step fill:#ffffff,stroke:#c3c2b7,color:#0b0b0b
    classDef ai fill:#e8f1fc,stroke:#2a78d6,color:#0b0b0b,stroke-width:2px
    classDef guard fill:#fbeeee,stroke:#d03b3b,color:#0b0b0b
    classDef agent fill:#f1effc,stroke:#6250d6,color:#0b0b0b
```

- **Sensor gateway** (`gateway.py`): encodes each value the way its protocol carries it (BACnet REAL, Modbus int16/uint16 × scale,
  SNMP integers), then decodes it with the point map (`registry.py`) and flags `out_of_range` (impossible value or saturated
  register), `no_data` and `comm_loss` (device did not answer). A real site swaps the simulated backend for a BACnet/Modbus/SNMP
  client with the same `read()` method.
- **Diagnostics** (`diagnostics.py`): limits with their sources (ISO 10816-1 vibration zones, ASHRAE TC 9.9 humidity, filter final
  ΔP, condenser approach, containment pressure), a straight-line trend through the daily means → **days until the next limit**,
  and an **N+1** check (can one CRAH alone carry the week's peak IT load?). A humidity sensor is cross-checked against the dew
  point from the CRAH return air, so a drifting sensor is reported as a sensor fault, not as humid room air.
- **Cooling constraint** → **safety rule R5**: a cooling-path warning (`no_raise`) means *never warmer than now*; a failure with no
  backup (`fallback`), e.g. a tripped CRAH, means *never warmer than now or than the fallback setpoint*. A critical pump with a
  healthy standby is `no_raise` (switch pumps). Advisory findings (UPS, humidity, sensor drift) do not constrain cooling.
- **Faults hidden in the test weeks** (they show in the equipment data days before any rack gets hot). First appearance, checked hourly:

  | Fault (starts) | Watch | Warning | Critical |
  |---|---|---|---|
  | CRAH-2 filter loading (15 Apr) | 21 Apr (projected 250 Pa within 7 days) | 27 Apr 19:00 · N+1 lost 27 Apr 18:00 | – |
  | CHWP-1 bearing wear (24 Apr) | 25 Apr | 27 Apr 15:00 (ISO zone C) | 2 May 09:00 (zone D) |
  | ENV-CA-2 humidity drift (22 Apr) | 25 Apr | 28 Apr 04:00 | – |
  | CH-1 condenser fouling (23 Apr) | 25 Apr | 30 Apr 01:00 | – |
  | CT-1 comm loss (26 Apr 14:00–16:00) | – | 26 Apr 14:00 | – |

  The healthy weeks raise no alarm (checked every 6 hours, 9 Feb – 14 Apr).
- The **closed-loop study is unchanged**: it has no hardware faults and passes no constraint, so the results below are the same.

## Security layer: `predictive_cooling/security/`

BACnet/IP and Modbus TCP, the protocols of the sensors and CRAH units, have **no authentication**: anyone on that network can
forge a reading, replay a recording or write a setpoint. The dangerous lie is a rack reported *cooler* than it is, which makes an
AI (or a rule) run the room warmer.

```mermaid
flowchart LR
    ATK(["Attacker"]):::guard -->|"forge · replay · write"| BMS["BMS network<br/>BACnet/IP · Modbus TCP"]:::step
    ATK -->|"prompt injection"| UI["Operator question"]:::step
    BMS --> SA["Security Analyst (S7)<br/>integrity model · replay · command audit"]:::agent
    PDU["PDUs · SNMP v3 authPriv<br/>separate network"]:::ok --> SA
    UI --> G1["G1 prompt screen"]:::guard
    SA --> R6["R6 · untrusted → never warmer"]:::guard
    G1 --> AG["Agents + G2 / G3"]:::agent
    R6 --> AG
    AG --> G4["G4 · redact, HMAC-sign, hash chain"]:::guard
    classDef step fill:#ffffff,stroke:#c3c2b7,color:#0b0b0b
    classDef ok fill:#e6f6ef,stroke:#1baf7a,color:#0b0b0b
    classDef guard fill:#fbeeee,stroke:#d03b3b,color:#0b0b0b
    classDef agent fill:#f1effc,stroke:#6250d6,color:#0b0b0b
```

| Defence | File | How |
|---|---|---|
| **Integrity model (ML)** | `integrity.py` | Per rack, least squares on the training weeks: inlet ≈ f(supply air, that rack's PDU power; now and 3 lags). Residual std **0.18 °C**; flagged when the reading is > 1.5 °C cooler than expected once, or > 1.0 °C twice in a row. **0 false alarms** on 2,682 validation + test readings. The PDUs sit on a separate SNMP v3 network, so an attacker must forge two systems. |
| **Replay detection** | `integrity.py` | Twelve noisy inlet readings never repeat exactly; a vector equal to one from the last day (agents: 26 h window; closed loop: 7 days) is a recording. |
| **Command-channel audit** | `commands.py` | Each CRAH's BACnet setpoint must equal what the control system commanded; a difference is an unauthorised write. The gateway itself is read-only. |
| **Rule R6** | `safety.py` | Untrusted data → never warmer than now or than the fallback setpoint. Runs in the closed-loop AI controller and in every agent case (status `security_alert`). |
| **G1 prompt screen** | `prompt_guard.py` | Unicode NFKC + removal of zero-width/control characters, then weighted patterns (instruction override, secret exfiltration, guard bypass, tool manipulation, out-of-policy setpoints, markup, encoded payloads). Score ≥ 3 blocks the case; 1–2 withholds the text from the models. |
| **G4 output guard** | `prompt_guard.py` | Redacts API keys (incl. the real values of the configured secrets), JWTs, links and e-mails from model notes; flags claims that equipment was changed. |
| **Signed recommendation** | `signing.py` | HMAC-SHA256 over the payload with `COMMAND_SIGNING_KEY` (ephemeral per process if unset), 15-minute expiry, one-time nonce, evidence hash. `CommandVerifier` is the actuator-gateway check (signature, key, expiry, nonce, 16–24 °C). |
| **Hash-chained trace** | `audit.py` | Every event carries sha256(previous hash + event); editing any stored event breaks the chain. |
| **Rate limit** | `ratelimit.py` | Paid model modes: 5 cases / 10 min per session, 40 / hour per app. |

**Closed-loop attack study** (14 test days, the attacks hit nightly GPU batches; the PDUs stay honest):

| Attack | Fixed 20 °C | Rule-based | AI + MPC *without* integrity check | **AI + MPC** |
|---|---|---|---|---|
| **Sensor spoofing**: B4–B6 read 2.5 °C cooler, 21 & 28 Apr 00:30–05:30 | 0 | 450 | 465 (peak 28.21 °C) | **0** (46 steps held by R6) |
| **Replay**: 27 Apr plays back Sunday night, 30 Apr plays back the evening before | 0 | 435 | 390 (peak 29.21 °C) | **0** (46 steps held by R6) |

Minutes with a true rack inlet above 27 °C. The integrity monitor never fires in the four non-attack scenarios, so the AI's
commands and every result above are identical with and without it. Limits: a forgery smaller than ~1 °C is not caught (the
forecaster's safety margin absorbs most of it), and an attacker who controls both the BMS and the PDU network is out of scope.

## The steps in code

| Step | File | What it does |
|---|---|---|
| ① | `dataset.py` | Builds the workload, weather, operating history and log faults |
| ② | `preprocess.py` | Reindexes to the full 15-minute grid → removes impossible values → catches stuck sensors (same value ≥ 6 times) → fills holes up to 1 hour, then splits by time into train (weeks 1–9), validation (10–11) and test (12–13) |
| ③ | `forecast.py` | Compares 3 models: **Persistence** (baseline), **Linear** and **Gradient Boosting** with physics-based monotonic constraints (higher setpoint → warmer racks, less chiller power). One model per target × horizon (3 × 4) |
| ④ | `mpc.py` | Builds the 81 plans, forecasts each one, rejects plans where `forecast + safety margin > 27 °C`, and picks the plan with the lowest cooling + IT energy. The margin is the 99th percentile of how much the model under-predicted on the validation weeks |
| ④ | `controllers.py` | Fixed / Rule-based / AI, plus **feedback correction**: the last forecast error is added to the next forecast (helps when the room drifts away from the training data) |
| ⑤ | `safety.py` | R1 missing sensor → fallback, R2 unfamiliar conditions → fallback, R3 near the limit → cool by 2 °C now, R4 at most ±1 °C per 15 minutes and within 16–24 °C (fallback = the previous fixed setpoint, proven safe) |
| ⑥ | `plant.py`, `evaluate.py` | The simulated room is the judge: 14-day closed-loop runs in 4 scenarios |
| | `pipeline.py` | Runs every step end to end and tunes the baselines on validation (fixed = highest setpoint that never overheated, rule = lowest-energy deadband that never overheated) |
| | `security/` | Security layer: `integrity.py` (ML integrity model, replay, closed-loop monitor), `commands.py` (command audit + verdict), `attacks.py` (simulated attacks), `prompt_guard.py` (G1/G4), `signing.py`, `audit.py`, `ratelimit.py`, `posture.py` (protocols + STRIDE) |
| | `hardware/` | Hardware layer: `registry.py` (22 devices, point map), `gateway.py` (poll + decode + quality), `telemetry.py` (equipment historian + injected faults), `diagnostics.py` (limits, trends, N+1, constraint) |
| | `agents/` | Agent layer: `engine.py` (LangGraph, G1–G4, S5), `tools.py` (the tools above), `llm_loops.py` (function-calling loops), `gemini.py` + `claude.py` (providers), `skills.py` + `skill_specs/` (S1–S7) |
| | `app.py` | Dashboard: “Ask the agents” tab + 6 tabs, one per step |

## Results (2 test weeks the model never saw)

### ③ Forecast accuracy

| Model | Inlet MAE 15 min | 30 min | 45 min | 60 min | Cooling NRMSE 60 min |
|---|---|---|---|---|---|
| Persistence (no AI) | 0.31 °C | 0.48 | 0.61 | 0.71 | 10.0 % |
| Linear regression | 0.19 °C | 0.25 | 0.30 | 0.34 | 7.0 % |
| **Gradient boosting** | **0.17 °C** | **0.17** | **0.18** | **0.18** | **3.5 %** |

This meets the proposal targets (MAE ≤ 1 °C at 15 minutes, NRMSE ≤ 10 %). Persistence is always late: it only notices the GPU batch after it has started.
The ML model learned from history that the batch starts at 01:00 on weekdays, so it sees it coming.

![forecast](docs/forecast-vs-actual.png)

### ④ How the MPC chooses

Like a GPS: try every route for the next hour, drop the ones that overheat, take the cheapest, drive only the first
15 minutes, then plan again with fresh data.

```mermaid
flowchart LR
    N["Setpoint now"]:::step --> C["Each 15 min:<br/>−1, 0 or +1 °C"]:::step
    C --> P["4 steps → 3⁴ =<br/>81 plans"]:::step
    P --> F["Forecast every plan"]:::ai
    F --> D{"peak + safety margin<br/>≤ 27 °C?"}:::guard
    D -- no --> X["Rejected"]:::guard
    D -- yes --> E["Cheapest safe plan<br/>(least kWh)"]:::ok
    E --> A["Apply only<br/>its first step"]:::ok
    classDef step fill:#ffffff,stroke:#c3c2b7,color:#0b0b0b
    classDef ai fill:#e8f1fc,stroke:#2a78d6,color:#0b0b0b,stroke-width:2px
    classDef guard fill:#fbeeee,stroke:#d03b3b,color:#0b0b0b
    classDef ok fill:#e6f6ef,stroke:#1baf7a,color:#0b0b0b
```

Example at 00:30, just before the GPU batch: 18 of the 81 plans are safe, and the cheapest is 21 → 21 → 21 → 22 °C.
It lowers the setpoint by 1 °C first to pre-cool for the 01:00 job.

![mpc](docs/mpc-81-plans.png)

### ⑥ Controllers compared (normal operation, 14 days)

| | Fixed 20 °C | Rule-based (tuned) | **AI + MPC** |
|---|---|---|---|
| Cooling energy | 12,512 kWh | 12,144 kWh | **11,892 kWh** |
| Facility energy (incl. the 0.2 kW AI server running 24/7) | 44,687 kWh | 44,319 kWh | **44,141 kWh** |
| PUE | 1.489 | 1.477 | **1.471** |
| Minutes with inlet > 27 °C | 0 | 0 | **0** |
| Average setpoint | 20.0 °C | 21.4 °C | 22.4 °C |
| Decision time per step | – | – | 24 ms (target < 10 s) |

```mermaid
xychart-beta
    title "Cooling energy over 14 test days (kWh, lower is better)"
    x-axis ["Fixed 20 °C", "Rule-based", "AI + MPC"]
    y-axis "kWh" 11500 --> 12700
    bar [12512, 12144, 11892]
```

The axis starts at 11,500 kWh to make the gap visible; most cooling energy is needed whatever the setpoint.

**Summary:** the AI cuts cooling energy by **5.0 %** vs the fixed setpoint and **2.1 %** vs the tuned rule-based controller.
Whole-building energy drops by 1.22 % / 0.40 % (about 57,000 / 18,500 THB per year at 4 THB/kWh), with no overheating at any point.

![results](docs/results-day.png)

> **An honest reading:** the proposal targeted ≥ 10 % cooling savings vs a tuned rule-based controller. In this simulated room the AI **falls short at 2.1 %** because:
> (1) rack B6 is a hot spot and the hottest rack 100 % of the time, which caps how warm the room can run;
> (2) inlets above 26 °C make the server fans speed up, so warmer is not always cheaper (the model knows this and stops);
> (3) the setpoint is the only control knob.
> Next steps: fix the airflow at B6 (blanking panels/containment) or add knobs such as chilled-water temperature and fan speed.

### ⑤ Fault tests (minutes with inlet > 27 °C)

The AI only *proposes*; four rules can override it before anything is sent (**R5** applies the Hardware Engineer's
constraint in agent cases, **R6** withholds the AI when the data fails the integrity check; see the hardware and security layers above):

```mermaid
flowchart LR
    P["MPC proposal"]:::ai --> R1{"R1 · sensor<br/>missing?"}:::guard
    R1 -- yes --> FB["Fallback setpoint"]:::ok
    R1 -- no --> R2{"R2 · conditions never<br/>seen in training?"}:::guard
    R2 -- yes --> FB
    R2 -- no --> R3{"R3 · rack already<br/>near 27 °C?"}:::guard
    R3 -- yes --> CO["Cool 2 °C now"]:::ok
    R3 -- no --> R4["R4 · max ±1 °C per step,<br/>stay within 16–24 °C"]:::guard
    R4 --> SEND["Send command"]:::ok
    classDef ai fill:#e8f1fc,stroke:#2a78d6,color:#0b0b0b,stroke-width:2px
    classDef guard fill:#fbeeee,stroke:#d03b3b,color:#0b0b0b
    classDef ok fill:#e6f6ef,stroke:#1baf7a,color:#0b0b0b
```

| Scenario | Fixed | Rule-based | AI + MPC | AI without safety filter |
|---|---|---|---|---|
| Normal | 0 | 0 | 0 | – |
| **B5/B6 sensors go offline** during the GPU batch | 0 | 210 | **0** (28 fallback steps) | 240 |
| **Room changed after training** (+20 % recirculation, chiller 10 % worse) | 1,980 | 150 | **60** | – |
| **Unplanned load surge** (+45–50 % on the GPU racks) | 0 | 0 | 15 (peak 27.03 °C) | – |

- The safety filter matters: without it, the AI trusts the remaining (cooler) sensors and lets the room overheat for 240 minutes.
- When the room changes, feedback correction cuts overheating from 240 to 60 minutes, but short exceedances remain when the batch starts. That is a signal to retrain.
- Nobody can forecast a job that has never happened before. The AI runs closer to the limit, so it is hit harder in the first 15 minutes; then R3 cools by 2 °C immediately.

## How to run

Requires Python 3.11+ (tested on 3.12). `requirements.txt` pins exact versions because the committed
`artifacts/bundle.pkl` is only reused when scikit-learn matches; otherwise the first start retrains (1–3 minutes).

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python -m predictive_cooling
```

The last command opens the dashboard at http://localhost:8501 (if `artifacts/bundle.pkl` is missing or was built with
another scikit-learn, it first trains and tests everything, about 1–3 minutes).
To run only the pipeline and print the result tables:

```bash
.venv/bin/python -m predictive_cooling.pipeline
```

Ask the agents from the command line:

```bash
.venv/bin/python -m predictive_cooling.agents --at "2026-04-21 00:30"
```

```bash
.venv/bin/python -m predictive_cooling.agents --at "2026-04-29 05:30"
```

```bash
.venv/bin/python -m predictive_cooling.agents --at "2026-04-21 00:30" --equipment-fault CRAH-1
```

```bash
.venv/bin/python -m predictive_cooling.agents --at "2026-04-21 02:00" --attack spoofing
```

Tests (90 tests including headless dashboard smoke tests, about 4.5 minutes):

```bash
.venv/bin/python -m pytest -q
```

## Deploy

LangGraph is a Python library that runs inside the Streamlit process, so the whole app is **one Streamlit service**.
Gemini, Claude and Supabase are optional and switched on by secrets.

```mermaid
flowchart LR
    U["Browser"]:::step --> A["Streamlit app<br/>app.py + LangGraph agents<br/>+ forecaster (bundle.pkl)"]:::ai
    A -. "agent mode = Gemini<br/>GEMINI_API_KEY" .-> G["Gemini API"]:::step
    A -. "agent mode = Claude<br/>ANTHROPIC_API_KEY" .-> CL["Claude API"]:::step
    A -. "SUPABASE_URL / SUPABASE_KEY" .-> D[("Supabase<br/>agent_cases")]:::ok
    classDef step fill:#ffffff,stroke:#c3c2b7,color:#0b0b0b
    classDef ai fill:#e8f1fc,stroke:#2a78d6,color:#0b0b0b,stroke-width:2px
    classDef ok fill:#e6f6ef,stroke:#1baf7a,color:#0b0b0b
```

**Streamlit Community Cloud (free)**

1. Push this branch to GitHub (`artifacts/bundle.pkl` is committed so the app starts without retraining).
2. On [share.streamlit.io](https://share.streamlit.io) → *Create app* → pick the repo, branch `claude-new-version`, main file `app.py`.
   Under *Advanced settings* choose **Python 3.12**.
3. Paste your secrets (template: `.streamlit/secrets.toml.example`). Every key is optional:
   - `GEMINI_API_KEY` (from Google AI Studio) enables the *Gemini* agent mode; set `GEMINI_MODEL = "gemini-3.5-flash-lite"` on a free key.
   - `ANTHROPIC_API_KEY` enables the *Claude* agent mode (Claude Haiku 5.5, billed per token).
   - `SUPABASE_URL` + `SUPABASE_KEY` enable the case history.
   - `COMMAND_SIGNING_KEY` (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`) signs recommendations with a key
     that survives restarts; without it the key is ephemeral.

**Supabase case history (optional)**

1. Create a Supabase project and run `supabase/migrations/001_agent_cases.sql`, then `002_allow_claude_agent_mode.sql`, in its SQL editor.
2. Put the project URL and the **server-side secret key** in the secrets. The key stays on the server (Streamlit code
   never runs in the browser); RLS is on and the public roles get no access to the table.
3. Every *Run case* in the agents tab is saved; *Case history (Supabase)* at the bottom of the tab shows the latest 20.
   If Supabase is down the case still runs and a toast says it was not saved.

For local runs, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` (git-ignored) or export the same
names as environment variables.

## Dashboard

Every tab starts with an **In short** box (the message in plain language) and, where it helps, a diagram of the step.

0. **Ask the agents**: pick a moment, a task (recommend / analyze), optional failed sensors, equipment trips or a simulated cyber attack, and the agent mode. You see the answer, a swimlane trace of who did what (G1 → Supervisor → G2 → Data Analyst → Security Analyst → Hardware Engineer → Cooling Advisor → G3 → G4), the G3 checklist, the Security Analyst's and Hardware Engineer's reports, the signed recommendation, the forecast vs the chosen plan and (with Supabase) the case history.
1. **Sensors**: floor map (heatmap of the 12 racks) for any day and time, the whole day as charts, a column dictionary and a CSV download.
2. **Clean data**: the problems found in each sensor, raw vs cleaned, and the train/validation/test split.
3. **Forecast**: error by horizon, forecast vs actual, feature importance, and **a what-if where you set a setpoint plan and see what the model predicts**.
4. **MPC decision**: pick a time and see all 81 plans (energy vs peak temperature), which ones are safe and which one was chosen.
5. **Safety**: the 4 rules, how often each one fired, and a zoomed chart of each fault.
6. **Results**: energy, PUE, the proposal §8.4 style table, and the 3 controllers on the same day.
7. **Hardware**: health of every device at any moment (with simulated trips), the findings with their limits and days to the next
   limit, 4-week trend panels of the hidden faults, rack power from the PDUs, and the gateway's raw-register → decoded view of any device.
8. **Security**: the attack surface, the closed-loop spoofing and replay attacks (true temperature, setpoint sent and the integrity
   residual), the integrity model's accuracy, a live prompt-screen playground, the STRIDE threat model and the protocol posture.

## Limitations

- All data is **mock** data from a simple physics model, not measurements from a real room. The numbers show *the method*, not guaranteed savings at a real site.
- The model and the plant were designed by the same person. Even though the forecaster never sees the equations, it should next be tested against another simulator (e.g. SustainDC) or real data.
- Nothing here controls real equipment. The system only recommends, in a simulated room.
- The security checks are tested against the simulated attacks in this repository, not a red team. Pattern-based prompt
  screening can be evaded by rephrasing; it is one layer, and the numbers stay safe because Python computes them and G3 re-checks them.

## File layout

```
app.py                       Streamlit dashboard
data/sensor_history.csv      mock dataset (committed, open it directly)
data/equipment_telemetry.csv equipment historian: 22 devices, 69 points (committed)
predictive_cooling/
  config.py                  all constants (limit, horizon, split dates, electricity price)
  plant.py                   ⑥ simulated room (the judge)
  dataset.py                 ① builds the sensor history
  preprocess.py              ② cleaning + data split
  forecast.py                ③ forecasting models
  mpc.py                     ④ 81-plan MPC
  safety.py                  ⑤ safety filter
  controllers.py             Fixed / Rule-based / AI controllers
  evaluate.py                closed-loop tests + fault scenarios
  pipeline.py                runs everything + saves artifacts/
  storage.py                 optional Supabase case history
  security/                  security layer
    integrity.py             ML integrity model (inlet vs PDU power + supply air), replay detection, closed-loop monitor
    commands.py              command-channel audit and the trusted/untrusted verdict
    attacks.py               simulated attacks: spoofing, replay, unauthorised setpoint write
    prompt_guard.py          G1 prompt-injection screen, G4 output redaction
    signing.py, audit.py     HMAC-signed recommendations, hash-chained trace
    ratelimit.py, posture.py rate limit for paid modes; protocol posture + STRIDE table
  hardware/                  hardware layer
    registry.py              22 field devices and their point map (protocol, address, encoding, scale)
    gateway.py               sensor gateway: poll, decode, quality flags
    telemetry.py             builds the equipment historian (with injected hardware faults)
    diagnostics.py           limits, trends -> days to limit, N+1 capacity, cooling constraint
  agents/                    agent layer (Supervisor, Data Analyst, Security Analyst, Hardware Engineer, Cooling Advisor)
    engine.py                LangGraph graph, G1/G2/G3, S5 compose, run_case()
    tools.py                 the tools agents may call (window ends at the case time)
    llm_loops.py             parent/child function-calling loops shared by the live modes
    gemini.py, claude.py     Gemini and Claude Haiku providers
    skills.py, skill_specs/  S1–S7 registry and instructions
tests/test_pipeline.py       tests for every step
tests/test_hardware.py       gateway, historian, diagnostics, rule R5 and the Hardware Engineer
tests/test_security.py       prompt screen, integrity model, replay, R6, signing, audit chain, attacks end to end
tests/test_agents.py         agent, guardrail, scripted-Gemini and mock-server Claude tests
tests/test_app.py            headless dashboard smoke tests (Streamlit AppTest)
tests/test_storage.py        Supabase history (off without keys, failures never break a case)
artifacts/bundle.pkl         trained models + test logs (committed for deployment)
supabase/migrations/         SQL for the optional agent_cases table
.streamlit/                  theme (config.toml) + secrets template
docs/                        README images
Midterm Project /            proposal report (PDF)
```

Branches: `main` = the earlier SustainDC/FastAPI/Supabase agent prototype; `claude` = the pipeline-only redesign (no agents); `claude-new-version` = this version (agent architecture + sensor data, trained forecaster and MPC).
