# Flows and upgrades

[Architecture index](README.md)

**Flows** (`hardware/flows.py`): at one moment, electricity from the sub-meters and PDUs (grid → UPS → rack groups; chiller,
CRAH fans, pumps + tower, lighting) and heat (servers + CRAH fans + walls → chilled water → condenser water with the
compressor's work → cooling tower → outdoor air). Both balance by construction; the Data center page draws them as Sankeys and
as a plant drawing.

**Upgrade study** (`hardware/upgrades.py`, run by `pipeline.py`): each option is a conservative plant-model change, run on the
two test weeks with the rule-based controller (hardware alone), today's AI, and, when the room's behaviour changes, the AI
retrained on a simulated 13-week history of the upgraded room (≈ 3 s). The study runs without the integrity monitor, which
would have to be re-baselined after any physical change.

| Option (example products) | Hardware alone | **With the AI** | Cooling | kWh/yr | THB/yr | tCO₂/yr | CAPEX (assumed) | Payback |
|---|---|---|---|---|---|---|---|---|
| UPS ESS mode (Eaton 93PM) | 1.98 % | **2.38 %** | 0.0 % | 27,384 | 109,537 | 12.0 | 0.03 M THB | **0.2 yr** |
| PM variable-speed pumps (Grundfos TPE3) | 0.30 % | **0.70 %** | 2.6 % | 8,090 | 32,360 | 3.5 | 0.40 M | 12.4 yr |
| EC fans in both CRAHs (ebm-papst RadiPac/RadiFit, or Liebert PCW) | 1.16 % | **1.56 %** | 5.8 % | 17,996 | 71,984 | 7.9 | 0.90 M | 12.5 yr |
| All of the above | 8.91 % | **9.28 %** | 25.6 % | 106,811 | 427,246 | 46.7 | 7.58 M | 17.7 yr |
| Cold-aisle containment (Vertiv SmartAisle or similar) | 0.46 % | **0.87 %** | 3.2 % | 10,051 | 40,203 | 4.4 | 0.75 M | 18.7 yr |
| Oil-free magnetic-bearing chiller (Danfoss Turbocor compressors) | 3.46 % | **3.85 %** | 14.3 % | 44,320 | 177,279 | 19.4 | 5.50 M | 31 yr |

Facility energy saved vs today's AI on today's room (1,151 MWh/yr, PUE 1.471), annualised from the two test weeks.

**Advisor** (`hardware/advisor.py`, skill S8): maintenance the current findings call for first (filter, bearing, condenser,
sensor), then options ranked by payback, with hardware-alone vs with-AI savings, tCO₂ (TGO 0.4371 t/MWh) and notes. CAPEX
values are budget assumptions (editable on the Upgrades page). With containment the AI sits at the 24 °C setpoint
ceiling 88 % of the time: the site's setpoint policy becomes the limit, not the racks.
