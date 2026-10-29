"""
Alert manager: turns a stream of readings into review-window snapshots.

WHY THIS EXISTS — the "different data rates" problem at alert level.
A motor sends 4 readings/hour, a compressor 1. If every reading became an
alert, motors would flood the queue simply because they report more often.

So the platform works in REVIEW WINDOWS (config.REVIEW_WINDOW_HOURS, 6 h):
at the end of each window the maintenance lead sees ONE row per machine,
built from that machine's LATEST reading. This gives every machine one vote
per window regardless of its sampling rate.

Each snapshot row also carries:
  age_min        how old the latest reading is at window end (freshness input)
  is_down        machine already failed and is under maintenance -> excluded
  target         GROUND TRUTH: machine fails within FAILURE_HORIZON_HOURS
                 after window end (used for evaluation only, never for ranking)
"""
import numpy as np
import pandas as pd

import config

# A reading older than this is treated as "machine not reporting".
MAX_READING_AGE_HOURS = 2 * config.REVIEW_WINDOW_HOURS


def window_ends(preds: pd.DataFrame, window_hours: int = config.REVIEW_WINDOW_HOURS):
    start = preds["timestamp"].min().floor("h")
    end = preds["timestamp"].max()
    step = pd.Timedelta(hours=window_hours)
    ends = pd.date_range(start + step, end, freq=step)
    return ends


def build_windows(preds: pd.DataFrame, window_hours: int = config.REVIEW_WINDOW_HOURS) -> pd.DataFrame:
    """One snapshot row per (window, machine) from the machine's latest reading."""
    preds = preds.sort_values("timestamp")
    lookback = pd.Timedelta(hours=MAX_READING_AGE_HOURS)
    horizon = config.FAILURE_HORIZON_HOURS
    frames = []
    for w, end in enumerate(window_ends(preds, window_hours)):
        recent = preds[(preds["timestamp"] > end - lookback) & (preds["timestamp"] <= end)]
        snap = recent.groupby("machine_id", sort=False).tail(1).copy()
        snap["window"] = w
        snap["window_end"] = end
        frames.append(snap)
    snaps = pd.concat(frames, ignore_index=True)

    snaps["age_min"] = (snaps["window_end"] - snaps["timestamp"]).dt.total_seconds() / 60
    next_failure = snaps["timestamp"] + pd.to_timedelta(snaps["time_to_failure_h"], unit="h")
    hours_to_failure = (next_failure - snaps["window_end"]).dt.total_seconds() / 3600
    snaps["is_down"] = hours_to_failure <= 0
    snaps["target"] = ((hours_to_failure > 0) & (hours_to_failure <= horizon)).astype(int)
    snaps = snaps[~snaps["is_down"]].drop(columns="is_down").reset_index(drop=True)
    return snaps


def mark_new_vs_ongoing(ranked: pd.DataFrame) -> pd.DataFrame:
    """
    Alert de-duplication across windows: a machine that stays in the top-k
    for consecutive windows is ONE ongoing issue, not a new alert each time.
    """
    ranked = ranked.sort_values(["machine_id", "window"]).copy()
    prev_in = ranked.groupby("machine_id")["in_top_k"].shift(1, fill_value=False)
    prev_win = ranked.groupby("machine_id")["window"].shift(1)
    consecutive = (ranked["window"] - prev_win) == 1
    ranked["alert_status"] = np.where(
        ~ranked["in_top_k"], "",
        np.where(prev_in & consecutive, "ongoing", "new"))
    return ranked.sort_values(["window", "rank"]).reset_index(drop=True)


def alert_volume_by_class(preds: pd.DataFrame, snaps: pd.DataFrame) -> pd.DataFrame:
    """Raw reading-level alerts vs window-level alerts per class (data-rate effect)."""
    raw = preds.groupby("machine_class").agg(readings=("predicted_alert", "size"),
                                             reading_level_alerts=("predicted_alert", "sum"))
    win = snaps.groupby("machine_class").agg(window_snapshots=("predicted_alert", "size"),
                                             window_level_alerts=("predicted_alert", "sum"))
    out = raw.join(win).reset_index()
    out["share_of_reading_alerts"] = out["reading_level_alerts"] / out["reading_level_alerts"].sum()
    out["share_of_window_alerts"] = out["window_level_alerts"] / out["window_level_alerts"].sum()
    return out
