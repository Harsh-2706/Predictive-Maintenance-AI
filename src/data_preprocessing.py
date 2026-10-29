"""
Cleaning, feature engineering and chronological splitting.

Key design decisions (explain these in the viva):

1. TIME-BASED rolling windows (config.ROLLING_WINDOWS, e.g. "2h", "6h").
   A motor sends 8 readings per 2h, a compressor sends 2. Windows defined in
   rows would compare different physical durations; windows in time do not.

2. `minutes_since_last` feature records the gap to the previous reading.
   The fusion engine also uses reading age for the data-freshness factor.

3. CHRONOLOGICAL split with a PURGE GAP.
   The label looks 24 h into the future. A training row 2 h before the
   train/val cutoff has a label that depends on what happens inside the
   validation period. Dropping the last FAILURE_HORIZON_HOURS before each
   cutoff removes that leakage.
"""
import numpy as np
import pandas as pd

import config


def clean(df):
    df = df.sort_values(["machine_id", "timestamp"]).drop_duplicates(["machine_id", "timestamp"])
    df = df.dropna(subset=["timestamp", "machine_id"]).reset_index(drop=True)
    return df


def add_features(df, sensors):
    """Per-machine, time-indexed rolling statistics plus trend features."""
    out = []
    for _, g in df.groupby("machine_id", sort=False):
        g = g.set_index("timestamp").sort_index()
        for s in sensors:
            for w in config.ROLLING_WINDOWS:
                roll = g[s].rolling(w, min_periods=1)
                g[f"{s}_mean_{w}"] = roll.mean()
                g[f"{s}_std_{w}"] = roll.std().fillna(0.0)
            # Short-term vs long-term mean: positive when the sensor is drifting.
            short, long = config.ROLLING_WINDOWS[0], config.ROLLING_WINDOWS[-1]
            g[f"{s}_trend"] = g[f"{s}_mean_{short}"] - g[f"{s}_mean_{long}"]
        g["minutes_since_last"] = (
            g.index.to_series().diff().dt.total_seconds().div(60).fillna(0.0).values
        )
        out.append(g.reset_index())
    return pd.concat(out, ignore_index=True)


def feature_columns(sensors):
    cols = list(sensors)
    for s in sensors:
        for w in config.ROLLING_WINDOWS:
            cols += [f"{s}_mean_{w}", f"{s}_std_{w}"]
        cols.append(f"{s}_trend")
    cols.append("minutes_since_last")
    return cols


def split_cutoffs():
    start = pd.Timestamp(config.SIM_START)
    total = pd.Timedelta(days=config.SIM_DAYS)
    train_end = start + total * config.TRAIN_FRAC
    val_end = start + total * (config.TRAIN_FRAC + config.VAL_FRAC)
    return train_end, val_end


def assign_split(df):
    """Label rows train / val / test by time; mark purge-gap rows as 'purged'."""
    train_end, val_end = split_cutoffs()
    gap = pd.Timedelta(hours=config.FAILURE_HORIZON_HOURS)
    ts = df["timestamp"]
    split = np.where(ts < train_end, "train", np.where(ts < val_end, "val", "test"))
    purge = ((ts >= train_end - gap) & (ts < train_end)) | ((ts >= val_end - gap) & (ts < val_end))
    split = np.where(purge, "purged", split)
    df = df.copy()
    df["split"] = split
    return df


def preprocess_class(df, machine_class, save=True):
    sensors = config.MACHINE_CLASSES[machine_class]["sensors"]
    df = add_features(clean(df), sensors)
    df = assign_split(df)
    if save:
        config.DATA_PROC_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(config.DATA_PROC_DIR / f"{machine_class}_processed.csv", index=False)
    return df


def load_processed(machine_class):
    path = config.DATA_PROC_DIR / f"{machine_class}_processed.csv"
    return pd.read_csv(path, parse_dates=["timestamp"])
