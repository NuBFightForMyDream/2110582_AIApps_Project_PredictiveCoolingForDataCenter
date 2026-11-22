# S8 — Plan Upgrades
Owner: hardware_engineer. Version: 0.5.0.

Only in `upgrade` mode, after `diagnose_equipment`. Call `evaluate_upgrades`: it lists the cheap
maintenance the diagnosis calls for (a loaded filter, a worn bearing, a fouled condenser) and ranks
every hardware option by simple payback: containment, EC fans, an oil-free chiller, variable-speed
pumps, the UPS energy-saver mode and all of them together. Each option was run in closed loop on the
upgraded plant model for the two test weeks, with the rule-based controller, with today's AI and with
the AI retrained for the upgraded room, so the savings are measured, not quoted from a brochure.

In your finish note: maintenance first, then the fastest payback and the largest saving, and how
much of it the hardware gives alone versus with the AI. Use only the tool's numbers. CAPEX values
are budget assumptions and savings are simulated; say so. Name products as examples of a class, not
as endorsements.
