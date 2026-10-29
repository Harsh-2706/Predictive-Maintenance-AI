"""
Load sensor data for each machine class.

Today the source is the simulator output in data/simulated/. If a real dataset
is added later, place it in data/raw/, convert it to the same columns
(timestamp, machine_id, machine_class, <sensors>, failure_label) and load it
here. Every downstream module only depends on this common schema.
"""
import pandas as pd

import config

REQUIRED_COLUMNS = ["timestamp", "machine_id", "machine_class", "failure_label"]


def load_class(machine_class):
    path = config.DATA_SIM_DIR / f"{machine_class}_raw.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python main.py --stage simulate")
    df = pd.read_csv(path, parse_dates=["timestamp"])
    missing = [c for c in REQUIRED_COLUMNS + config.MACHINE_CLASSES[machine_class]["sensors"]
               if c not in df.columns]
    if missing:
        raise ValueError(f"{machine_class}: missing columns {missing}")
    return df


def load_all():
    return {c: load_class(c) for c in config.MACHINE_CLASSES}


def load_failure_events():
    return pd.read_csv(config.DATA_SIM_DIR / "failure_events.csv", parse_dates=["failure_time"])
