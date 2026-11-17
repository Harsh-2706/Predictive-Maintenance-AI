"""
Score a plant's own sensor file with the trained models.

Input: a CSV of raw readings, one row per reading:
    timestamp, machine_id, machine_class, <sensors for that class>
    motor       temperature, vibration, rpm
    pump        pressure, flow_rate, temperature
    compressor  temperature, pressure, vibration
Rows may come from several machines and classes in one file. Include at least
the last 6 hours per machine: the models read 2 h and 6 h trends.

Output: one row per machine, from its LATEST reading, with the same pipeline
as the live system: features -> trained model -> calibrated risk -> remaining
life -> priority (risk x consequence x data freshness) -> crew queue.
Data freshness is measured against the newest timestamp in the file.

The checks below fail loudly on bad input (wrong class, missing sensor,
unparseable time) instead of scoring garbage.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd

import config
from src.data_preprocessing import add_features, clean
from src.fusion_engine import freshness_factor

MAX_ROWS = 200_000
MAX_MACHINES = 500
MIN_HISTORY_H = 6
REQUIRED = ["timestamp", "machine_id", "machine_class"]


def read_csv(data: bytes | str) -> pd.DataFrame:
    text = data.decode("utf-8-sig") if isinstance(data, bytes) else data
    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as e:  # noqa: BLE001 - surface the parser's message
        raise ValueError(f"Could not read the CSV: {e}") from e
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing column(s): {', '.join(missing)}. Required: {', '.join(REQUIRED)} + sensors.")
    if df.empty:
        raise ValueError("The file has no rows.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"Too many rows ({len(df):,}); the limit is {MAX_ROWS:,}.")
    df = df.copy()
    df["machine_class"] = df["machine_class"].astype(str).str.strip().str.lower()
    df["machine_id"] = df["machine_id"].astype(str).str.strip()
    unknown = sorted(set(df["machine_class"]) - set(config.MACHINE_CLASSES))
    if unknown:
        raise ValueError(f"Unknown machine_class value(s): {', '.join(unknown)}. "
                         f"Use one of: {', '.join(config.MACHINE_CLASSES)}.")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    bad_ts = int(df["timestamp"].isna().sum())
    if bad_ts == len(df):
        raise ValueError("No timestamp could be read. Use a format like 2026-04-17 06:00:00.")
    if bad_ts:
        warnings.append(f"{bad_ts} row(s) with an unreadable timestamp were skipped.")
        df = df[df["timestamp"].notna()]
    if df["machine_id"].nunique() > MAX_MACHINES:
        raise ValueError(f"Too many machines ({df['machine_id'].nunique()}); the limit is {MAX_MACHINES}.")
    classes_per_machine = df.groupby("machine_id")["machine_class"].nunique()
    if (classes_per_machine > 1).any():
        raise ValueError("Machine(s) listed under more than one class: "
                         + ", ".join(classes_per_machine[classes_per_machine > 1].index[:5]))
    for cls in df["machine_class"].unique():
        need = config.MACHINE_CLASSES[cls]["sensors"]
        lacking = [s for s in need if s not in df.columns]
        if lacking:
            raise ValueError(f"{cls} rows need sensor column(s): {', '.join(lacking)}.")
        for s in need:
            df[s] = pd.to_numeric(df[s], errors="coerce")
        part = df[df["machine_class"] == cls]
        n_nan = int(part[need].isna().any(axis=1).sum())
        if n_nan:
            warnings.append(f"{n_nan} {cls} row(s) with missing or non-numeric sensor values were skipped.")
    keep = np.ones(len(df), dtype=bool)
    for cls in df["machine_class"].unique():
        m = (df["machine_class"] == cls).to_numpy()
        keep[m] &= df.loc[m, config.MACHINE_CLASSES[cls]["sensors"]].notna().all(axis=1).to_numpy()
    df = df[keep]
    if df.empty:
        raise ValueError("No usable rows after removing incomplete readings.")
    return df, warnings


def score(df: pd.DataFrame, bundles: dict, calibrators: dict, rul_bundles: dict | None = None,
          k: int = config.TOP_K) -> dict:
    """Latest-reading risk, remaining life and crew queue for every machine in `df`."""
    from src.rul import predict_frame

    df, warnings = validate(df)
    now = df["timestamp"].max()
    rows = []
    for cls, part in df.groupby("machine_class"):
        sensors = config.MACHINE_CLASSES[cls]["sensors"]
        feats = add_features(clean(part[REQUIRED + sensors]), sensors)
        latest = feats.sort_values("timestamp").groupby("machine_id").tail(1).set_index("machine_id")
        history = feats.groupby("machine_id")["timestamp"].agg(lambda t: (t.max() - t.min()).total_seconds() / 3600)
        b = bundles[cls]
        raw = b["model"].predict_proba(latest[b["features"]])[:, 1]
        risk = calibrators[cls].predict(raw)
        out = pd.DataFrame({"machine_id": latest.index, "machine_class": cls,
                            "reading_time": latest["timestamp"].to_numpy(),
                            "raw": raw, "risk": risk, "history_h": history.reindex(latest.index).to_numpy()})
        if rul_bundles and cls in rul_bundles:
            r = predict_frame(rul_bundles[cls], latest)
            out[["rul_h", "rul_low_h", "rul_high_h"]] = r.to_numpy()
        rows.append(out)
    res = pd.concat(rows, ignore_index=True)
    res["age_min"] = (now - res["reading_time"]).dt.total_seconds() / 60
    res["severity"] = res["machine_class"].map(config.SEVERITY_WEIGHTS)
    res["freshness"] = freshness_factor(res["age_min"])
    res["priority"] = res["risk"] * res["severity"] * res["freshness"]
    res = res.sort_values(["priority", "raw", "machine_id"], ascending=[False, False, True]).reset_index(drop=True)
    res["rank"] = np.arange(1, len(res) + 1)
    res["in_queue"] = res["rank"] <= k
    short = res[res["history_h"] < MIN_HISTORY_H]
    if len(short):
        warnings.append(f"{len(short)} machine(s) have less than {MIN_HISTORY_H} h of history "
                        f"({', '.join(short['machine_id'][:5])}{'…' if len(short) > 5 else ''}); "
                        "their trend features are less reliable.")
    return {"as_of": now, "k": k, "machines": res, "warnings": warnings,
            "rows_used": int(len(df)), "classes": sorted(df["machine_class"].unique())}


def sample_csv(raw: dict[str, pd.DataFrame], end: pd.Timestamp, hours: int = 12) -> str:
    """Raw readings of every machine for the `hours` before `end`: a ready-to-upload example."""
    parts = []
    for cls, df in raw.items():
        sensors = config.MACHINE_CLASSES[cls]["sensors"]
        p = df[(df["timestamp"] > end - pd.Timedelta(hours=hours)) & (df["timestamp"] <= end)]
        parts.append(p[REQUIRED + sensors])
    out = pd.concat(parts, ignore_index=True).sort_values(["timestamp", "machine_id"])
    num = out.select_dtypes("number").columns
    out[num] = out[num].round(3)
    return out.to_csv(index=False)
