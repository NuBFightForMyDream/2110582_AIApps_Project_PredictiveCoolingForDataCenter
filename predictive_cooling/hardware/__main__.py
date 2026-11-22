"""`python -m predictive_cooling.hardware` — (re)build data/equipment_telemetry.csv from the plant run."""
from .. import config as C
from .registry import DEVICES
from .telemetry import build

if __name__ == "__main__":
    frame = build()
    print(f"Wrote {len(frame):,} rows x {frame.shape[1]} points from {len(DEVICES)} devices to "
          f"{C.EQUIPMENT_PATH.relative_to(C.ROOT)}")
