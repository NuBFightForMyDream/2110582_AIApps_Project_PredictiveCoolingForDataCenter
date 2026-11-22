"""Equipment historian: what the 22 field devices reported every 15 minutes (data/equipment_telemetry.csv).

`python -m predictive_cooling.hardware` writes the file. It is derived from the same plant run as
data/sensor_history.csv (same seeds, so room temperatures, IT power and meter readings agree), plus the
physics the room-level log does not need: chilled-water and condenser-water temperatures, pump flow, filter
pressure drop, humidity, containment pressure and the power of each rack PDU.

Hardware faults are injected in the last weeks so the Hardware Engineer has something to find. They are early
warnings: they show in the equipment data before they would show as hot racks, which is the point of
watching the hardware directly.
"""
import numpy as np
import pandas as pd

from .. import config as C
from ..dataset import make_exogenous, simulate_history
from ..plant import PlantParams
from .registry import (CHW_DESIGN_FLOW_M3H, CHILLER_RATED_KW, CRAH_RATED_AIRFLOW_M3H, CRAH_RATED_KW, DEVICES,
                       REGISTRY, UPS_RATED_KW)

SEED = C.DATASET_SEED + 100
FILTER_CHANGE_DAYS = 56          # CRAH filters are replaced every 8 weeks (2 Feb, 30 Mar)
CLEAN_FILTER_PA = 110.0          # pressure drop of a clean filter at 100 % fan speed
FILTER_AIRFLOW_LOSS = 0.0012     # airflow lost per Pa of extra filter pressure drop

FAULTS = [
    dict(device="CRAH-2", start="2026-04-15", code="FILTER_LOADING",
         story="Dust from building work next door loads the CRAH-2 filter ~8 Pa/day: airflow and N+1 capacity drop."),
    dict(device="CH-1", start="2026-04-23", code="CONDENSER_FOULING",
         story="Scale builds up in the chiller condenser tubes: the condenser approach rises 0.25 °C/day."),
    dict(device="CHWP-1", start="2026-04-24", code="BEARING_WEAR",
         story="The duty chilled-water pump's bearing wears: vibration grows exponentially (×2 every ~3.6 days)."),
    dict(device="ENV-CA-2", start="2026-04-22", code="SENSOR_DRIFT",
         story="The row-B humidity sensor drifts +0.7 %RH/day; the CRAH return-air humidity shows the room did not change."),
    dict(device="CT-1", start="2026-04-26 14:00", hours=2, code="COMM_LOSS",
         story="The cooling-tower controller stops answering Modbus polls for 2 hours (network switch reboot)."),
]


def rh_from_dew_point(temp_c, dew_c):
    """Relative humidity (%) from air temperature and dew point (Magnus formula)."""
    a, b = 17.625, 243.04
    return 100 * np.exp(a * dew_c / (b + dew_c)) / np.exp(a * temp_c / (b + temp_c))


def dew_point(temp_c, rh_pct):
    a, b = 17.625, 243.04
    g = np.log(np.clip(rh_pct, 0.1, 100) / 100) + a * temp_c / (b + temp_c)
    return b * g / (a - g)


def wet_bulb(temp_c, rh_pct):
    """Stull (2011) wet-bulb approximation, °C."""
    t, rh = np.asarray(temp_c, float), np.asarray(rh_pct, float)
    return (t * np.arctan(0.151977 * np.sqrt(rh + 8.313659)) + np.arctan(t + rh) - np.arctan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * np.arctan(0.023101 * rh) - 4.686035)


def filter_airflow_ratio(dp100_pa):
    return np.clip(1 - FILTER_AIRFLOW_LOSS * (np.asarray(dp100_pa) - CLEAN_FILTER_PA), 0.5, 1.0)


def build_frame(exo=None, history=None) -> pd.DataFrame:
    exo = make_exogenous() if exo is None else exo
    hist = simulate_history(exo) if history is None else history
    idx = hist.index
    n = len(idx)
    rng = np.random.default_rng(SEED)
    day = np.asarray((idx - idx[0]) / pd.Timedelta(days=1), dtype=float)
    hour = np.asarray(idx.hour + idx.minute / 60, dtype=float)

    def since(start):
        return np.clip(np.asarray((idx - pd.Timestamp(start)) / pd.Timedelta(days=1), dtype=float), 0, None)

    def noise(sd):
        return rng.normal(0, sd, n)

    out = {}
    put = lambda dev, point, values: out.__setitem__(REGISTRY[dev].column(point), np.asarray(values, float))  # noqa: E731

    outdoor = hist["outdoor_temp_c"].to_numpy()
    it_kw = hist["it_power_kw"].to_numpy()
    speed = hist["crah_fan_pct"].to_numpy() / 100
    supply = hist["supply_air_c"].to_numpy()
    ret = hist["return_air_c"].to_numpy()
    setpoint_in_use = hist["crah_setpoint_c"].shift(1).fillna(20.0).to_numpy()
    heat_kw = it_kw + PlantParams().envelope_kw_per_c * (outdoor - 24.0)           # sensible load into the room
    load_kw = heat_kw + hist["crah_fan_kw"].to_numpy()                             # CRAH fan heat ends in the water too

    # Room humidity: the CRAH humidity control holds the dew point near 9.5 °C.
    room_dew = 9.5 + 0.5 * np.sin(2 * np.pi * (hour - 14) / 24) + _ar1(rng, n, 0.98, 0.05)

    # --- CRAH-1 / CRAH-2 -------------------------------------------------------------------
    since_change = day % FILTER_CHANGE_DAYS
    dp100 = {1: CLEAN_FILTER_PA + 1.2 * since_change + noise(1.5),
             2: CLEAN_FILTER_PA + 2 + 1.2 * since_change + 8.0 * since("2026-04-15") + noise(1.5)}
    for u in (1, 2):
        dev = f"CRAH-{u}"
        ratio = filter_airflow_ratio(dp100[u])
        share = 0.5 * (dp100[u] / dp100[1]) ** 0.3                                  # a loaded filter makes the fan work harder
        put(dev, "status", np.ones(n))
        put(dev, "setpoint_c", setpoint_in_use)
        put(dev, "supply_air_c", supply + (0.12 if u == 2 else -0.08) + noise(0.08))
        put(dev, "return_air_c", ret + noise(0.12))
        put(dev, "return_rh_pct", rh_from_dew_point(ret, room_dew) + noise(0.4))
        put(dev, "fan_speed_pct", 100 * speed)
        put(dev, "fan_kw", hist["crah_fan_kw"].to_numpy() * share)
        put(dev, "airflow_m3h", CRAH_RATED_AIRFLOW_M3H * speed * ratio * (1 + noise(0.006)))
        put(dev, "filter_dp_pa", dp100[u] * speed ** 2)
        put(dev, "chw_valve_pct", np.clip(100 * (heat_kw / 2) / (0.9 * CRAH_RATED_KW) / ratio + noise(0.8), 5, 100))

    # --- chilled water: CH-1 + CHWP-1 (duty) / CHWP-2 (standby) -----------------------------
    chiller_kw = hist["chiller_kw"].to_numpy()
    flow = CHW_DESIGN_FLOW_M3H + noise(0.12)
    chws = 9.0 + 0.3 * (supply - 18.0) + noise(0.06)
    rh_out = np.clip(78 - 2.2 * (outdoor - 28) + noise(2.0), 40, 98)
    wb = wet_bulb(outdoor, rh_out)
    rejected = load_kw + chiller_kw
    ct_speed = np.clip(30 + 0.3 * rejected + 3 * (wb - 25), 20, 100)
    ct_approach = 6.2 - 2.6 * ct_speed / 100 + noise(0.08)
    cond_in = wb + ct_approach
    cond_out = cond_in + rejected / (1.163 * 30.0)                                  # 30 m³/h condenser water
    put("CH-1", "status", np.ones(n))
    put("CH-1", "load_pct", 100 * load_kw / CHILLER_RATED_KW)
    put("CH-1", "kw", chiller_kw)
    put("CH-1", "cop", load_kw / chiller_kw)
    put("CH-1", "chws_c", chws)
    put("CH-1", "chwr_c", chws + load_kw / (1.163 * flow))                          # 1.163 kWh per m³·K of water
    put("CH-1", "cond_in_c", cond_in)
    put("CH-1", "cond_out_c", cond_out)
    put("CH-1", "cond_approach_c", 1.2 + noise(0.05) + 0.25 * since("2026-04-23"))

    vib = 0.9 * np.exp(since("2026-04-24") / 5.2) + noise(0.04)
    pump_kw = 2.1 * (1 + noise(0.01))
    put("CHWP-1", "status", np.ones(n))
    put("CHWP-1", "speed_hz", 48.0 + noise(0.05))
    put("CHWP-1", "flow_m3h", flow)
    put("CHWP-1", "kw", pump_kw)
    put("CHWP-1", "vibration_mm_s", vib)
    put("CHWP-1", "bearing_temp_c", 42 + 4 * (vib - 0.9) + 0.1 * (outdoor - 29) + noise(0.3))
    put("CHWP-2", "status", np.zeros(n))
    for point in ("speed_hz", "flow_m3h", "kw", "vibration_mm_s"):
        put("CHWP-2", point, np.zeros(n))
    put("CHWP-2", "bearing_temp_c", 30 + 0.2 * (outdoor - 29) + noise(0.3))

    put("CT-1", "status", np.ones(n))
    put("CT-1", "fan_speed_pct", ct_speed)
    put("CT-1", "kw", np.clip(hist["pump_tower_kw"].to_numpy() - pump_kw, 0.5, None))
    put("CT-1", "wet_bulb_c", wb)
    put("CT-1", "cold_water_c", cond_in)
    put("CT-1", "approach_c", ct_approach)

    # --- power: UPS-1 and the 12 rack PDUs --------------------------------------------------
    put("UPS-1", "output_source", np.full(n, 3.0))                                  # 3 = normal (UPS-MIB)
    put("UPS-1", "load_pct", 100 * it_kw / UPS_RATED_KW)
    put("UPS-1", "output_kw", it_kw)
    put("UPS-1", "battery_temp_c", 24.8 + 0.4 * np.sin(2 * np.pi * (hour - 15) / 24) + noise(0.2))
    put("UPS-1", "efficiency_pct", 100 / (1 + PlantParams().ups_loss_fraction) + noise(0.05))

    params = PlantParams()
    cap = np.asarray(params.capacity_kw, float)
    util = exo[[f"util_{r}" for r in C.RACKS]].to_numpy()
    inlet = hist[C.INLET_COLS].to_numpy()
    fans = params.server_fan_fraction * cap * (1 + params.server_fan_gain * np.clip(inlet - params.server_fan_knee_c, 0, None)) ** 3
    rack_kw = cap * (params.idle_fraction + (1 - params.idle_fraction) * util) + fans
    for i, rack in enumerate(C.RACKS):
        put(f"PDU-{rack}", "power_kw", rack_kw[:, i] * (1 + noise(0.004)))

    # --- room sensors ----------------------------------------------------------------------
    row_a = hist[[f"inlet_{r}_c" for r in C.ROWS["A"]]].mean(axis=1).to_numpy()
    row_b = hist[[f"inlet_{r}_c" for r in C.ROWS["B"]]].mean(axis=1).to_numpy()
    for dev, temp, drift in (("ENV-CA-1", row_a, 0.0), ("ENV-CA-2", row_b, 0.7)):
        put(dev, "temp_c", temp + noise(0.08))
        put(dev, "rh_pct", rh_from_dew_point(temp, room_dew) + noise(0.35) + drift * since("2026-04-22"))
    mean_ratio = (filter_airflow_ratio(dp100[1]) + filter_airflow_ratio(dp100[2])) / 2
    put("ENV-DP-1", "aisle_dp_pa", 3.2 + 12 * (mean_ratio - 1) - 0.012 * (it_kw - 88) + noise(0.12))

    frame = pd.DataFrame(out, index=idx)[[c for d in DEVICES for c in d.columns]]
    begin = pd.Timestamp("2026-04-26 14:00")
    frame.loc[begin:begin + pd.Timedelta(hours=2) - pd.Timedelta(minutes=1), REGISTRY["CT-1"].columns] = np.nan
    frame.index.name = "timestamp"
    return _round(frame)


def _ar1(rng, n, phi, sd):
    x = np.zeros(n)
    e = rng.normal(0, sd, n)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def _round(frame):
    """Store each point at the resolution its register carries."""
    for d in DEVICES:
        for p in d.points:
            digits = 2 if p.encoding == "real" else max(0, int(round(-np.log10(p.scale))))
            frame[d.column(p.name)] = frame[d.column(p.name)].round(digits)
    return frame


def build(path=C.EQUIPMENT_PATH):
    frame = build_frame()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index_label="timestamp")
    return frame


def load(path=C.EQUIPMENT_PATH):
    if not path.exists():
        return build(path)
    return pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
