# Flows and upgrades

[Architecture index](README.md)

**Flows** (`hardware/flows.py`): at one moment, electricity from the sub-meters and PDUs (grid → UPS → rack groups; chiller,
CRAH fans, pumps + tower, lighting) and heat (servers + CRAH fans + walls → chilled water → condenser water with the
compressor's work → cooling tower → outdoor air). Both balance by construction; the Live plant page draws them as Sankeys and
as a plant drawing.

**Upgrade study** (`hardware/upgrades.py`, run by `pipeline.py`): each option is a conservative plant-model change, run on the
two test weeks with the rule-based controller (hardware alone), today's AI, and, when the room's behaviour changes, the AI
retrained on a simulated 13-week history of the upgraded room (≈ 3 s). The study runs without the integrity monitor, which
would have to be re-baselined after any physical change.

| Option | Plant change | Facility saved (with the AI) | Payback |
|---|---|---|---|
| UPS energy-saver mode | UPS losses 5 % → 1.5 % | 2.38 % | 0.2 yr |
| PM variable-speed pumps | pumps + tower −14 % | 0.70 % | 12.4 yr |
| EC fans | CRAH fan power −30 % | 1.56 % | 12.5 yr |
| All together | all five | 9.28 % (46.7 tCO₂/yr) | 17.7 yr |
| Cold-aisle containment | recirculation halved | 0.87 % | 18.7 yr |
| Oil-free chiller | COP +25 %, +5 %/°C | 3.85 % | 31 yr |

**Advisor** (`hardware/advisor.py`, skill S8): maintenance the current findings call for first (filter, bearing, condenser,
sensor), then options ranked by payback, with hardware-alone vs with-AI savings, tCO₂ (TGO 0.4371 t/MWh) and notes. CAPEX
values are budget assumptions (editable on the Upgrade advisor page). With containment the AI sits at the 24 °C setpoint
ceiling 88 % of the time: the site's setpoint policy becomes the limit, not the racks.
