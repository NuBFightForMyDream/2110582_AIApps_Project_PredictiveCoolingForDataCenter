"""Energy and heat flows through the room at one moment (for the Sankey diagrams and the plant schematic).

    electricity:  grid -> UPS -> rack PDUs (compute / storage+web / GPU) + UPS losses
                  grid -> chiller, CRAH fans, pumps + tower, lighting
    heat:         servers + CRAH fans + walls -> chilled water (CRAH coils) -> chiller evaporator
                  chiller evaporator + compressor work -> condenser water -> cooling tower -> outdoor air

Electricity comes from the room log's sub-meters; the rack split comes from the PDUs; water-side temperatures and
the chiller load from the equipment historian. The heat Sankey balances by construction: chilled water = servers +
CRAH fans + walls (heat leaking in), rejected = chilled water + compressor work.
"""
import pandas as pd

from .. import config as C
from ..plant import PlantParams
from .registry import CHILLER_RATED_KW

GROUPS = {"Compute racks (A1–A6)": C.ROWS["A"], "Storage + web (B1–B3)": ["B1", "B2", "B3"], "GPU racks (B4–B6)": ["B4", "B5", "B6"]}
KW_PER_TR = 3.517


def balance(room: pd.Series, eq: pd.Series) -> dict:
    """room: one clean row of the sensor log; eq: the equipment-historian row at the same time."""
    p = PlantParams()
    it, cooling, facility = float(room["it_power_kw"]), float(room["cooling_kw"]), float(room["facility_kw"])
    other = max(facility - it - cooling, 0.0)
    lighting = min(p.lighting_kw, other)
    racks = {r: float(eq[f"PDU-{r}.power_kw"]) for r in C.RACKS}
    scale = it / sum(racks.values()) if sum(racks.values()) > 0 else 1.0       # PDUs and the UPS meter differ by ~1 %
    groups = {name: scale * sum(racks[r] for r in members) for name, members in GROUPS.items()}
    envelope = max(0.0, p.envelope_kw_per_c * (float(room["outdoor_temp_c"]) - 24.0))
    load = float(eq["CH-1.load_pct"]) / 100 * CHILLER_RATED_KW
    chiller = float(room["chiller_kw"])
    return {
        "power": {"facility": facility, "it": it, "ups_loss": other - lighting, "lighting": lighting, "chiller": chiller,
                  "crah_fans": float(room["crah_fan_kw"]), "pumps_tower": float(room["pump_tower_kw"]), "groups": groups,
                  "racks": racks},
        "heat": {"it": it, "crah_fans": float(room["crah_fan_kw"]), "walls": envelope,
                 "chilled_water": it + float(room["crah_fan_kw"]) + envelope, "compressor": chiller,
                 "rejected": it + float(room["crah_fan_kw"]) + envelope + chiller},
        "kpi": {"pue": facility / it, "cooling_per_it": cooling / it, "cop": load / chiller if chiller else float("nan"),
                "kw_per_tr": chiller / (load / KW_PER_TR) if load else float("nan"),
                "chw_delta_c": float(eq["CH-1.chwr_c"] - eq["CH-1.chws_c"]),
                "air_delta_c": float(room["return_air_c"] - room["supply_air_c"]),
                "load_pct": float(eq["CH-1.load_pct"]), "chiller_load_kw": load,
                "hottest_inlet_c": float(room[C.INLET_COLS].max())},
    }
