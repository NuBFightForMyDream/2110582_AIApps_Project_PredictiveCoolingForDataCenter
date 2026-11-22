"""Hardware upgrades as physical changes to the plant model, and how they combine with the AI.

Each option changes the plant parameters the way that class of product changes a real room, conservatively
against the vendor claims in catalog.py. The study runs the two test weeks on the upgraded plant with:
    rule      the tuned rule-based controller (hardware alone)
    ai        today's AI (its forecaster was trained on the old room)
    ai_new    the AI retrained on a simulated 13-week history of the upgraded room (physical + AI)
Savings are measured by the plant against today's AI on today's room, then annualised.

After any physical change the sensor-integrity model must be re-baselined too: a contained room is cooler than
the old physics model expects and would look "forged". The study therefore runs without the integrity monitor.
"""
from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .. import config as C
from ..plant import PlantParams
from .catalog import GRID_EMISSION_T_PER_MWH, UPGRADE_PRODUCTS


@dataclass(frozen=True)
class Upgrade:
    key: str
    title: str
    change: str                  # what changes in the plant model
    products: tuple              # keys into catalog.UPGRADE_PRODUCTS
    capex_thb: tuple             # (low, high) budget assumption for this 12-rack room, not a quote
    retrain: bool                # does the room's thermal or energy response change enough to retrain the AI?
    note: str = ""

    def apply(self, p: PlantParams) -> PlantParams:
        return EFFECTS[self.key](p)


def _containment(p):
    return replace(p, recirc_c=tuple(r * 0.5 for r in p.recirc_c))


def _ec_fans(p):
    return replace(p, crah_fan_rated_kw=p.crah_fan_rated_kw * 0.7)


def _chiller(p):
    return replace(p, cop_ref=p.cop_ref * 1.25, cop_gain_per_c=0.05)


def _pumps(p):
    return replace(p, pump_tower_fraction=0.06)


def _ess(p):
    return replace(p, ups_loss_fraction=0.015)


EFFECTS = {"containment": _containment, "ec_fans": _ec_fans, "oil_free_chiller": _chiller, "pm_pumps": _pumps, "ups_ess": _ess}
EFFECTS["package"] = lambda p: _ess(_pumps(_chiller(_ec_fans(_containment(p)))))

UPGRADES = {
    "containment": Upgrade("containment", "Cold-aisle containment + blanking panels",
                           "Hot-air recirculation into every rack halved (B6 hot spot most)", ("containment",),
                           (600_000, 900_000), True, "Fixes the B6 hot spot that caps how warm the room can run."),
    "ec_fans": Upgrade("ec_fans", "EC fans in both CRAHs", "CRAH fan power −30 % at the same airflow (vendor claims up to 50 %)",
                       ("ec_fans", "crah_replacement"), (700_000, 1_100_000), False),
    "oil_free_chiller": Upgrade("oil_free_chiller", "Oil-free magnetic-bearing chiller",
                                "Chiller COP +25 % and +5 %/°C (was +4 %) for warmer water (vendor claims up to 50 % IPLV)",
                                ("oil_free_chiller",), (4_500_000, 6_500_000), True,
                                "Best done when the screw chiller reaches end of life."),
    "pm_pumps": Upgrade("pm_pumps", "Permanent-magnet variable-speed pumps",
                        "Pumps + tower power −14 % (pump share of the 7 % per kW of heat)", ("pm_pumps",), (300_000, 500_000), False),
    "ups_ess": Upgrade("ups_ess", "UPS energy-saver (ESS) mode", "UPS losses 5 % → 1.5 % of IT power", ("ups_ess",), (0, 50_000), False,
                       "A setting, not a purchase: needs a site risk review (the UPS switches to double conversion on "
                       "disturbances)."),
    "package": Upgrade("package", "All of the above", "All five changes together", tuple(UPGRADE_PRODUCTS), (6_100_000, 9_050_000),
                       True),
}


def retrained_forecaster(params: PlantParams):
    """Simulate the 13-week history on the upgraded room (same workload, weather and operator) and retrain."""
    from .. import dataset, forecast, preprocess
    history = dataset.simulate_history(dataset.make_exogenous(), params)
    clean, _ = preprocess.clean(history[dataset.COLUMNS])
    train, val, _ = preprocess.split(clean)
    model = forecast.Forecaster("gbm").fit(train)
    return model, forecast.safety_margins(model, val)


def economics(table: pd.DataFrame, baseline: dict, days: float, capex: dict | None = None) -> pd.DataFrame:
    """Annualised savings vs today's AI on today's room: kWh, THB, tCO2 and simple payback (mid-range CAPEX)."""
    out = table.copy()
    factor = 365.0 / days
    out["saved_kwh_yr"] = (baseline["facility_kwh"] - out["facility_kwh"]) * factor
    out["saved_cooling_pct"] = 100 * (1 - out["cooling_kwh"] / baseline["cooling_kwh"])
    out["saved_facility_pct"] = 100 * (1 - out["facility_kwh"] / baseline["facility_kwh"])
    out["saved_thb_yr"] = out["saved_kwh_yr"] * C.ELECTRICITY_THB_PER_KWH
    out["saved_tco2_yr"] = out["saved_kwh_yr"] * GRID_EMISSION_T_PER_MWH / 1000
    capex = capex or {k: sum(u.capex_thb) / 2 for k, u in UPGRADES.items()}
    out["capex_thb"] = out["upgrade"].map(capex)
    out["payback_years"] = np.where(out["saved_thb_yr"] > 0, out["capex_thb"] / out["saved_thb_yr"].clip(lower=1e-9), np.inf)
    return out
