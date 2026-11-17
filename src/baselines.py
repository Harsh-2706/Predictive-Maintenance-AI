"""
Baselines: is the AI actually better than what plants already do?

Every approach below gets the SAME crew capacity (config.TOP_K machines per
REVIEW_WINDOW_HOURS shift) and is scored on the SAME held-out test windows,
so the comparison is like-for-like.

  reactive      Run to failure. No predictive inspections; every failure is a
                breakdown. This is the cost reference for the savings calculator.
  schedule      Time-based preventive maintenance. The crew works through the
                fleet in a fixed rotation (machine-id order), k machines per shift,
                regardless of condition. Each machine is visited every
                ceil(60 / k) shifts.
  threshold     Classic condition-monitoring alarms (what a SCADA/PLC limit does).
                A machine alarms when any sensor is more than THRESHOLD_SIGMA
                standard deviations away from its healthy level, using the latest
                reading only. The crew visits the k alarms with the largest
                deviation; fewer if fewer machines alarm.
  ai            Our system: trained model -> calibrated risk -> priority S3
                (risk x consequence x data freshness), top k.

Scoring
  * recall_at_k     share of machine-shifts that end in failure within 24 h
                    that the crew was sent to (same definition as fusion_engine).
  * precision_at_k  share of crew visits that were to such a machine.
  * events_caught   failure events where the machine was visited in at least one
                    shift ending in the 24 h before the failure. We assume a visit
                    in that window finds the fault: generous to the baselines.
  * warning_h       for caught events, hours between the first such visit and
                    the failure.

A paired bootstrap over shifts gives a 95% interval for (AI - baseline) recall.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

import config
from src.data_preprocessing import load_processed, split_cutoffs

THRESHOLD_SIGMA = 3.0
HEALTHY_MIN_HOURS = 72          # "healthy" = more than 3 days before a failure
APPROACHES = {
    "reactive": "Run to failure (no predictive maintenance)",
    "schedule": "Fixed-rotation preventive inspections",
    "threshold": f"Sensor alarm limits ({THRESHOLD_SIGMA:g} sigma)",
    "ai": "AI: calibrated risk x consequence x freshness",
}

# Example costs for the savings calculator (INR). They are placeholders for a
# plant's own figures and are shown as editable inputs in the web app.
DEFAULT_COSTS = {
    "downtime_cost_per_hour": 25000,     # lost production per hour of a stopped machine
    "breakdown_downtime_hours": 8,       # unplanned failure: wait for parts + emergency repair
    "planned_downtime_hours": 2,         # planned repair in a scheduled slot
    "breakdown_repair_cost": 60000,      # emergency repair, secondary damage, overtime
    "planned_repair_cost": 20000,        # parts + labour when caught early
    "inspection_cost": 1500,             # one crew visit
}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
def healthy_stats() -> dict:
    """Per-class sensor mean/std over healthy TRAINING readings (no test data used)."""
    train_end, _ = split_cutoffs()
    out = {}
    for cls, spec in config.MACHINE_CLASSES.items():
        df = load_processed(cls)
        h = df[(df["timestamp"] < train_end) & (df["split"] == "train")
               & (df["time_to_failure_h"] > HEALTHY_MIN_HOURS)]
        out[cls] = {s: {"mean": float(h[s].mean()), "std": float(h[s].std())} for s in spec["sensors"]}
    return out


def load_ai_ranking(strategy: str = "S3_risk_priority") -> pd.DataFrame:
    return pd.read_csv(config.PREDICTIONS_DIR / f"ranked_alerts_{strategy}.csv",
                       parse_dates=["window_end"])


def attach_latest_sensors(snaps: pd.DataFrame) -> pd.DataFrame:
    """Add the raw sensor values of each snapshot's latest reading."""
    # Snapshot timestamp = window_end - age_min.
    snaps = snaps.copy()
    snaps["timestamp"] = (snaps["window_end"] - pd.to_timedelta(snaps["age_min"], unit="min")).dt.round("s")
    parts = []
    for cls, spec in config.MACHINE_CLASSES.items():
        p = load_processed(cls)[["timestamp", "machine_id"] + spec["sensors"]]
        p["timestamp"] = p["timestamp"].dt.round("s")
        parts.append(p)
    sensors = pd.concat(parts, ignore_index=True)
    out = snaps.merge(sensors, on=["timestamp", "machine_id"], how="left")
    if len(out) != len(snaps):
        raise ValueError("Duplicate readings while attaching sensors to snapshots")
    return out


# ---------------------------------------------------------------------------
# Selection rules (each returns snaps with a boolean `visited` column)
# ---------------------------------------------------------------------------
def select_reactive(snaps: pd.DataFrame, k: int) -> pd.DataFrame:
    return snaps.assign(visited=False, score=0.0)


def select_schedule(snaps: pd.DataFrame, k: int) -> pd.DataFrame:
    fleet = sorted(snaps["machine_id"].unique())
    pos = {m: i for i, m in enumerate(fleet)}
    n = len(fleet)
    snaps = snaps.copy()
    w0 = snaps["window"].min()
    # Shift w visits the k machines at rotation positions [(w*k) mod n, ... +k).
    offset = ((snaps["window"] - w0) * k) % n
    rel = (snaps["machine_id"].map(pos) - offset) % n
    snaps["visited"] = rel < k
    snaps["score"] = -rel.astype(float)
    return snaps


def select_threshold(snaps: pd.DataFrame, k: int, stats: dict, sigma: float = THRESHOLD_SIGMA) -> pd.DataFrame:
    snaps = snaps.copy()
    z = np.zeros(len(snaps))
    for cls, sensors in stats.items():
        m = (snaps["machine_class"] == cls).to_numpy()
        for s, st in sensors.items():
            zs = np.abs((snaps.loc[m, s].to_numpy() - st["mean"]) / st["std"])
            z[m] = np.maximum(z[m], np.nan_to_num(zs))
    snaps["score"] = z
    snaps["alarm"] = z >= sigma
    order = snaps.sort_values(["window", "score", "machine_id"], ascending=[True, False, True])
    order["slot"] = order.groupby("window").cumcount()
    snaps["visited"] = False
    picked = order[(order["slot"] < k) & order["alarm"]].index
    snaps.loc[picked, "visited"] = True
    return snaps


def select_ai(snaps: pd.DataFrame, k: int) -> pd.DataFrame:
    """Snapshots already ranked by the fusion engine (rank 1 = highest priority)."""
    if "rank" not in snaps.columns:
        raise ValueError("AI selection needs the ranked alerts (rank column).")
    return snaps.assign(visited=snaps["rank"] <= k, score=snaps["priority_score"])


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def test_failures(snaps: pd.DataFrame) -> pd.DataFrame:
    ev = pd.read_csv(config.DATA_SIM_DIR / "failure_events.csv", parse_dates=["failure_time"])
    start = snaps["window_end"].min()
    end = snaps["window_end"].max() + pd.Timedelta(hours=config.FAILURE_HORIZON_HOURS)
    ev = ev[(ev["failure_time"] > start) & (ev["failure_time"] <= end)].reset_index(drop=True)
    return ev


def event_outcomes(visited: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Per failure event: was it eligible (machine reported in the 24 h before), caught, warning hours."""
    horizon = pd.Timedelta(hours=config.FAILURE_HORIZON_HOURS)
    by_machine = {m: g for m, g in visited.groupby("machine_id")}
    rows = []
    for ev in events.itertuples():
        g = by_machine.get(ev.machine_id)
        if g is None:
            rows.append({"eligible": False, "caught": False, "warning_h": np.nan})
            continue
        before = g[(g["window_end"] < ev.failure_time) & (g["window_end"] >= ev.failure_time - horizon)]
        hit = before[before["visited"]]
        rows.append({
            "eligible": not before.empty,
            "caught": not hit.empty,
            "warning_h": (ev.failure_time - hit["window_end"].min()).total_seconds() / 3600 if not hit.empty else np.nan,
        })
    return pd.concat([events.reset_index(drop=True), pd.DataFrame(rows)], axis=1)


def score_approach(visited: pd.DataFrame, events: pd.DataFrame) -> dict:
    t = visited["target"] == 1
    v = visited["visited"]
    ev = event_outcomes(visited, events)
    el = ev[ev["eligible"]]
    days = (visited["window_end"].max() - visited["window_end"].min()).total_seconds() / 86400 \
        + config.REVIEW_WINDOW_HOURS / 24
    return {
        "inspections": int(v.sum()),
        "recall_at_k": float((t & v).sum() / max(t.sum(), 1)),
        "precision_at_k": float((t & v).sum() / max(v.sum(), 1)),
        "wasted_visits": int((v & ~t).sum()),
        "failure_events": int(len(el)),
        "events_caught": int(el["caught"].sum()),
        "events_missed": int(len(el) - el["caught"].sum()),
        "event_catch_rate": float(el["caught"].mean()) if len(el) else float("nan"),
        "median_warning_h": float(el["warning_h"].median()) if el["caught"].any() else float("nan"),
        "days": days,
    }


def per_window_recall(visited: pd.DataFrame) -> pd.DataFrame:
    g = visited.assign(hit=(visited["target"] == 1) & visited["visited"]).groupby("window")
    return pd.DataFrame({"targets": g["target"].sum(), "hits": g["hit"].sum()})


def paired_bootstrap(a: pd.DataFrame, b: pd.DataFrame, iters: int = config.BOOTSTRAP_ITERS) -> tuple[float, float]:
    """95% CI of recall(a) - recall(b), resampling shifts with replacement."""
    j = a.join(b, lsuffix="_a", rsuffix="_b")
    rng = np.random.default_rng(config.RANDOM_SEED)
    idx = rng.integers(0, len(j), size=(iters, len(j)))
    ta, ha, hb = j["targets_a"].to_numpy(), j["hits_a"].to_numpy(), j["hits_b"].to_numpy()
    tot = ta[idx].sum(1)
    d = (ha[idx].sum(1) - hb[idx].sum(1)) / np.maximum(tot, 1)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return float(lo), float(hi)


def run_baselines(k: int = config.TOP_K, save: bool = True) -> dict:
    ranked = load_ai_ranking()
    snaps = attach_latest_sensors(ranked)
    stats = healthy_stats()
    events = test_failures(snaps)

    selections = {
        "reactive": select_reactive(snaps, k),
        "schedule": select_schedule(snaps, k),
        "threshold": select_threshold(snaps, k, stats),
        "ai": select_ai(snaps, k),
    }
    rows, per_class = [], []
    win = {a: per_window_recall(s) for a, s in selections.items()}
    for a, s in selections.items():
        r = {"approach": a, "description": APPROACHES[a], **score_approach(s, events)}
        if a != "ai":
            lo, hi = paired_bootstrap(win["ai"], win[a])
            r["ai_recall_gain"] = score_approach(selections["ai"], events)["recall_at_k"] - r["recall_at_k"]
            r["ai_recall_gain_ci_low"], r["ai_recall_gain_ci_high"] = lo, hi
        rows.append(r)
        for cls, g in s.groupby("machine_class"):
            sc = score_approach(g, events[events["machine_class"] == cls])
            per_class.append({"approach": a, "machine_class": cls, **sc})

    comparison = pd.DataFrame(rows)
    by_class = pd.DataFrame(per_class)
    meta = {"k": k, "threshold_sigma": THRESHOLD_SIGMA, "healthy_stats": stats,
            "schedule_cycle_shifts": math.ceil(snaps["machine_id"].nunique() / k)}
    if save:
        config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
        comparison.round(4).to_csv(config.METRICS_DIR / "baseline_comparison.csv", index=False)
        by_class.round(4).to_csv(config.METRICS_DIR / "baseline_per_class.csv", index=False)
        (config.METRICS_DIR / "baseline_run.json").write_text(json.dumps(meta, indent=2))
    return {"comparison": comparison, "per_class": by_class, "meta": meta, "selections": selections}


# ---------------------------------------------------------------------------
# Savings calculator
# ---------------------------------------------------------------------------
def savings(comparison: pd.DataFrame, costs: dict | None = None, period_days: float = 30.0) -> dict:
    """
    Monthly maintenance cost of each approach, from its test-period outcomes.

      caught event  -> planned repair:  planned_downtime_hours x downtime cost + planned_repair_cost
      missed event  -> breakdown:       breakdown_downtime_hours x downtime cost + breakdown_repair_cost
      every visit   -> inspection_cost

    Outcomes are scaled from the test period to `period_days`.
    """
    c = {**DEFAULT_COSTS, **(costs or {})}
    bad = [key for key, v in c.items() if key in DEFAULT_COSTS and (v is None or v < 0)]
    if bad:
        raise ValueError(f"Costs must be zero or positive: {bad}")
    breakdown = c["breakdown_downtime_hours"] * c["downtime_cost_per_hour"] + c["breakdown_repair_cost"]
    planned = c["planned_downtime_hours"] * c["downtime_cost_per_hour"] + c["planned_repair_cost"]

    rows = []
    for r in comparison.itertuples():
        scale = period_days / r.days
        caught, missed, visits = r.events_caught * scale, r.events_missed * scale, r.inspections * scale
        cost_breakdowns, cost_planned, cost_visits = missed * breakdown, caught * planned, visits * c["inspection_cost"]
        rows.append({
            "approach": r.approach, "breakdowns": missed, "planned_repairs": caught, "inspections": visits,
            "downtime_hours": missed * c["breakdown_downtime_hours"] + caught * c["planned_downtime_hours"],
            "cost_breakdowns": cost_breakdowns, "cost_planned_repairs": cost_planned,
            "cost_inspections": cost_visits, "total": cost_breakdowns + cost_planned + cost_visits,
        })
    out = pd.DataFrame(rows).set_index("approach")
    ref = out.loc["reactive", "total"]
    out["saving_vs_reactive"] = ref - out["total"]
    out["saving_pct"] = 100 * out["saving_vs_reactive"] / ref if ref else 0.0
    return {"costs": c, "period_days": period_days,
            "cost_per_breakdown": breakdown, "cost_per_planned_repair": planned,
            "rows": out.reset_index()}


def load_comparison() -> pd.DataFrame:
    return pd.read_csv(config.METRICS_DIR / "baseline_comparison.csv")
