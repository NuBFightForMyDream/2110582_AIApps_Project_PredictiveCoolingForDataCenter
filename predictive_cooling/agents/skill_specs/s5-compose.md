# S5 — Compose Recommendation
Owner: supervisor. Version: 0.5.0.

Explain only results that passed G3. The headline, setpoint and every number are written by
Python from the verified evidence. State clearly that the data comes from a mock room and a
simplified plant model, that savings are simulated, and that nothing was sent to equipment.

When the Security Analyst found the data untrusted, say so first: which check failed (forged
readings, replay, unauthorised setpoint write), that the AI was withheld and that safety rule R6
keeps the room no warmer than now while it returns to the fallback setpoint.

Report the hardware result too: overall equipment health, the cooling constraint and the
findings behind it (device, value, limit, days to the next limit, maintenance action).

When the data was not ready, say which sensors failed and that safety rule R1 returns the room to
the proven fallback setpoint. Model notes (Gemini / Claude modes) are shown separately and never replace
the verified statement.
