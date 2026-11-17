"""
Technician feedback: close the loop between the AI and the shop floor.

When the crew inspects a machine from the queue they record what they found:
    fault_found   a real developing fault (the alert was right)
    no_fault      nothing wrong (false alarm)
    not_checked   could not inspect (access, production, parts)

Why it matters
  * Live precision: the share of checked alerts that were real, measured on
    the plant's own floor rather than on historical test data.
  * New training labels: confirmed faults and confirmed false alarms are the
    most valuable labels a plant can collect. `training_labels()` exports them
    in the same shape as the training data, ready for the next retraining run.

Storage is a plain CSV (data/feedback/feedback.csv) so it is easy to audit and
to replace with a database later. Writes are serialised with a lock.
"""
from __future__ import annotations

import csv
import threading
from datetime import datetime, timezone

import pandas as pd

import config

FEEDBACK_DIR = config.ROOT / "data" / "feedback"
FEEDBACK_PATH = FEEDBACK_DIR / "feedback.csv"
OUTCOMES = {"fault_found": "Fault found", "no_fault": "No fault found", "not_checked": "Not checked"}
COLUMNS = ["recorded_at", "machine_id", "machine_class", "window", "window_end", "risk",
           "queue_rank", "outcome", "note"]
MAX_NOTE = 300
_lock = threading.Lock()


def record(entry: dict, path=None) -> dict:
    path = path or FEEDBACK_PATH
    if entry.get("outcome") not in OUTCOMES:
        raise ValueError(f"outcome must be one of {list(OUTCOMES)}")
    note = " ".join(str(entry.get("note") or "").split())[:MAX_NOTE]
    row = {c: entry.get(c) for c in COLUMNS}
    row.update(note=note, recorded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            if new:
                w.writeheader()
            w.writerow(row)
    return row


def load(path=None) -> pd.DataFrame:
    path = path or FEEDBACK_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    return pd.read_csv(path)


def summary(path=None) -> dict:
    df = load(path)
    recent = df.tail(25).iloc[::-1]
    checked = df[df["outcome"].isin(["fault_found", "no_fault"])]
    by_class = []
    for cls in config.MACHINE_CLASSES:
        c = checked[checked["machine_class"] == cls]
        by_class.append({"machine_class": cls, "checked": int(len(c)),
                         "fault_found": int((c["outcome"] == "fault_found").sum()),
                         "confirmed_precision": float((c["outcome"] == "fault_found").mean()) if len(c) else None})
    return {
        "total": int(len(df)),
        "counts": {k: int((df["outcome"] == k).sum()) for k in OUTCOMES},
        "confirmed_precision": float((checked["outcome"] == "fault_found").mean()) if len(checked) else None,
        "by_class": by_class,
        "recent": recent.astype(object).where(recent.notna(), None).to_dict("records"),
    }


def training_labels(path=None) -> pd.DataFrame:
    """Confirmed outcomes as labels: machine_id, window_end, label (1 fault, 0 no fault)."""
    df = load(path)
    df = df[df["outcome"].isin(["fault_found", "no_fault"])].copy()
    df["label"] = (df["outcome"] == "fault_found").astype(int)
    return df[["machine_id", "machine_class", "window_end", "label"]].drop_duplicates(
        ["machine_id", "window_end"], keep="last").reset_index(drop=True)
