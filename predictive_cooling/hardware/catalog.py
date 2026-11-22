"""What is installed in the mock room, which instruments measure it, and which products could replace it.

Named products are real product families, listed with the vendor-published facts this project relies on and the
page they come from (checked Nov 2026). Units without a verified model are described by class ("legacy ..."):
the mock room is not a real site, and no vendor endorses these figures. Simulation parameters (capacities, COP,
fan power) are this project's own plant model, not datasheet values.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    vendor: str
    model: str
    category: str
    facts: str                   # vendor-published facts used here (verify against the current datasheet)
    source: str = ""
    note: str = ""


# ---- installed equipment (one entry per device in registry.py) ---------------------------------
INSTALLED = {
    "CRAH-1": Product("—", "Legacy chilled-water CRAH, AC belt-driven centrifugal fans (class)", "Cooling",
                      "Site model: 140 kW sensible at full airflow, 34,000 m³/h, 14 kW fan power per pair at 100 % speed",
                      note="Belt-driven AC fans are the main retrofit target (see EC fans)."),
    "CRAH-2": Product("—", "Legacy chilled-water CRAH, AC belt-driven centrifugal fans (class)", "Cooling",
                      "Same as CRAH-1; panel pre-filters, final ΔP ≈ 250 Pa", note="Filter loading in the test weeks."),
    "CH-1": Product("—", "Fixed-speed water-cooled screw chiller, 250 kW ≈ 71 TR (class)", "Cooling",
                    "Site model: COP 3.6 at 18 °C supply air / 30 °C outdoor, +4 % COP per °C warmer supply air"),
    "CHWP-1": Product("—", "End-suction pump, induction motor on a VFD at fixed speed (class)", "Cooling",
                      "Site model: 24 m³/h, ≈ 2.1 kW; duty pump"),
    "CHWP-2": Product("—", "End-suction pump, induction motor on a VFD at fixed speed (class)", "Cooling",
                      "Standby pump, starts automatically when CHWP-1 trips"),
    "CT-1": Product("—", "Induced-draft cooling tower + condenser-water pump skid (class)", "Cooling",
                    "Site model: approach 3.6–5.2 °C depending on fan speed"),
    "UPS-1": Product("Eaton", "93PM UPS, 200 kVA", "Power",
                     "30–200 kW range at unity power factor; up to 97 % in double conversion, > 99 % in Energy Saver System "
                     "(ESS) mode", "https://www.eaton.com/content/dam/eaton/products/backup-power-ups-surge-it-power-distribution/"
                     "backup-power-ups/eaton-93pm-ups/eaton-93pm-ups-30-250kva-datasheet-ps153029en.pdf",
                     note="Site model assumes 95 % (5 % loss) today; ESS is an upgrade option."),
    "ENV-CA-1": Product("APC by Schneider Electric", "NetBotz Temperature/Humidity Sensor AP9335TH", "Sensor",
                        "±2 °C (0–40 °C); ±4 %RH (20–90 %RH at 25 °C)",
                        "https://www.manualsdir.com/manuals/42152/apc-netbotz-nbrk0200.html?page=28",
                        note="Read through a NetBotz rack monitor; the site gateway publishes it as Modbus TCP."),
    "ENV-CA-2": Product("APC by Schneider Electric", "NetBotz Temperature/Humidity Sensor AP9335TH", "Sensor",
                        "±2 °C (0–40 °C); ±4 %RH (20–90 %RH at 25 °C)",
                        "https://www.manualsdir.com/manuals/42152/apc-netbotz-nbrk0200.html?page=28",
                        note="The one that drifts in the test weeks."),
    "ENV-DP-1": Product("Setra", "Model 264 very-low differential pressure transducer, 0–0.1 in. W.C. (0–25 Pa)", "Sensor",
                        "Ranges from 0–0.1 in. W.C.; ±1 % FS standard accuracy (≈ ±0.25 Pa on this range)",
                        "https://www.setra.com/products/pressure/model-264-low-differential-pressure-transducer",
                        note="Listed as discontinued by Honeywell: plan a like-for-like replacement."),
}
for _rack in ("A1", "A2", "A3", "A4", "A5", "A6", "B1", "B2", "B3", "B4", "B5", "B6"):
    INSTALLED[f"PDU-{_rack}"] = Product("Raritan (Legrand)", "PX3 intelligent rack PDU", "Power",
                                        "±1 % billing-grade metering (ISO/IEC 62053-21) on PX3 models; SNMPv3 with encryption",
                                        "https://review.raritan.com/products/power/power-distribution/rack-pdu/tech-specs",
                                        note="Trusted second source for the integrity model (separate SNMP v3 network).")

# ---- instruments inside the devices and on the room log ------------------------------------------
INSTRUMENTS = [
    ("Rack inlet temperature (×12, room log)", Product(
        "APC by Schneider Electric", "NetBotz Temperature Sensor AP9335T", "Sensor", "±2 °C from 0 to 40 °C",
        "https://community.se.com/t5/EcoStruxure-IT-forum/Netbotz-sensors-accuracy/td-p/208583",
        note="±2 °C is wider than the 1 °C the integrity check tolerates: calibrate yearly, or a drifted probe can look forged.")),
    ("Electrical sub-meters (chiller, CRAH fans, pumps + tower, facility)", Product(
        "Schneider Electric", "PowerLogic PM5560", "Sensor", "Class 0.2S active energy (IEC 62053-22); Modbus TCP and BACnet/IP "
        "over two Ethernet ports", "https://www.se.com/au/en/product/METSEPM5560/power-meter-powerlogic-pm5560-2-ethernet-up-to-63th-harmonic-11mb-4di-2do-52-alarms")),
    ("Chilled-water flow (CHWP-1/2)", Product(
        "Siemens", "SITRANS F M MAG 5100 W sensor + MAG 5000 transmitter", "Sensor",
        "±0.4 % of rate ± 1 mm/s including the sensor (with MAG 5000)",
        "https://www.siemens.com/global/en/products/automation/process-instrumentation/flow-measurement/electromagnetic/"
        "sitrans-f-m-mag-5100-w-for-water-applications.html")),
    ("Pump vibration (CHWP-1/2)", Product(
        "ifm", "VKV021 vibration transmitter", "Sensor", "0–25 mm/s RMS, 10–1000 Hz, 4–20 mA, monitoring to DIN ISO 10816; "
        "error < ±3 % of final value", "https://www.ifm.com/us/en/product/VKV021",
        note="Feeds the BEARING_WEAR rule (ISO 10816-1 zones C/D at 1.8 / 4.5 mm/s).")),
]

# ---- replacement / upgrade products ----------------------------------------------------------------
UPGRADE_PRODUCTS = {
    "containment": Product("Vertiv", "SmartAisle cold-aisle containment (or any cold-aisle containment + blanking panels)",
                           "Airflow", "Vendor claim: up to 27 % lower energy with cold-aisle containment",
                           "https://www.vertiv.com/en-us/products-catalog/facilities-enclosures-and-racks/integrated-solutions/smartaisle/"),
    "ec_fans": Product("ebm-papst", "RadiPac / RadiFit EC centrifugal fan retrofit", "Cooling",
                       "Vendor claim: up to 50 % fan energy vs AC belt-driven fans; same installation size",
                       "https://www.ebmpapst.com/sg/en/ec-fan-solutions/fan-retrofit.html"),
    "crah_replacement": Product("Vertiv", "Liebert PCW chilled-water CRAH with EC fans", "Cooling",
                                "Family 25–400 kW; EC fans cut motor energy 10–30 % vs standard AC motors (vendor)",
                                "https://www.vertiv.com/en-us/products-catalog/thermal-management/room-cooling/"
                                "vertiv-liebert--pcw-chilled-water-floor-mount-cooling-unit/"),
    "oil_free_chiller": Product("Danfoss (compressor)", "Water-cooled chiller with Turbocor oil-free magnetic-bearing "
                                "compressors", "Cooling", "Vendor claim: IPLV up to 50 % better than a comparably sized screw "
                                "chiller; integrated VFD; earlier series ≈ 140–540 kW", "https://danfoss.com/en/products/compressors/dcs/turbocor"),
    "pm_pumps": Product("Grundfos", "TPE3 in-line pump (permanent-magnet motor, integrated speed control, AUTOADAPT)", "Cooling",
                        "Range up to 22 kW; integrated variable speed", "https://product-selection.grundfos.com/products/tp-tpe/tpe3-i"),
    "ups_ess": Product("Eaton", "93PM Energy Saver System (ESS) mode", "Power", "> 99 % efficiency in ESS (vendor)",
                       "https://www.eaton.com/content/dam/eaton/products/backup-power-ups-surge-it-power-distribution/"
                       "backup-power-ups/eaton-93pm-ups/eaton-93pm-ups-30-250kva-datasheet-ps153029en.pdf"),
}

GRID_EMISSION_T_PER_MWH = 0.4371      # TGO electricity emission factor (EF Elec), Thailand 2022, latest year confirmed
GRID_EMISSION_SOURCE = "https://ghgreduction.tgo.or.th/en/download/download/13065/3377/32.html"   # TGO grid EF table
