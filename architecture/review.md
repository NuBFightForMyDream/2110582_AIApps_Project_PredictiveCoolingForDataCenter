# Review: limits and next steps

[Architecture index](README.md)

| Area | Limit | Next step |
|---|---|---|
| Data | Mock room from one physics model; the same author built model and plant | Test on another simulator or a real site's history |
| Savings | 2.1 % vs a tuned rule, short of the 10 % target (B6 hot spot, server fans above 26 °C, one knob) | More knobs (chilled-water temperature, fan speed); containment + a wider setpoint policy |
| Live LLM modes | Tested with scripted providers and a mock Claude server; the last live Gemini run predates two agents | A live acceptance run per provider |
| Hardware | Faults are injected and early-warning only (they do not change room temperatures) | Couple equipment faults to the plant; real BMS adapter |
| Security | Forgeries under ~1 °C pass; an attacker on both networks is out of scope; pattern-based prompt screening can be rephrased around | Re-baseline the integrity model after physical changes; red-team the prompt screen |
| Upgrades | CAPEX are budget assumptions; effects are modelled conservatively, not measured on site | Vendor quotes; post-upgrade measurement and verification |
| Actuation | None: the system only recommends | Any real actuation must verify the G4 signature and keep a human in the loop |
