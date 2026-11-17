"""
Model health: is the AI still seeing the kind of data it was trained on?

After deployment, sensors get replaced or recalibrated, machines get new
loads, seasons change. A model trained on last year's data can quietly get
worse. This module watches for that, two ways:

1. Data drift (no labels needed, works from day one)
   Population Stability Index (PSI) per sensor, comparing each week of new
   readings with the TRAINING period:
       PSI = sum over bins (cur% - ref%) * ln(cur% / ref%)
   Bins are the 10 deciles of the training data. Industry rule of thumb:
       < 0.10 stable   0.10-0.25 watch   > 0.25 drift: investigate / retrain
   The same check runs on the model's own output (score drift).

2. Performance tracking (needs outcomes, so it lags by the 24 h horizon)
   Weekly recall, precision and Brier score per class on the test period,
   to spot a model that is losing its edge.

`inject` lets the web app demonstrate detection: shift one sensor by a
percentage (e.g. a mis-calibrated temperature probe reading 8% high) and
watch the PSI react.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

import config
from src.data_preprocessing import load_processed

PSI_BINS = 10
PSI_WATCH, PSI_DRIFT = 0.10, 0.25
EPS = 1e-4


def psi_status(v: float) -> str:
    return "stable" if v < PSI_WATCH else ("watch" if v < PSI_DRIFT else "drift")


def bin_edges(ref: np.ndarray, bins: int = PSI_BINS) -> np.ndarray:
    edges = np.unique(np.quantile(ref[~np.isnan(ref)], np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    return edges


def shares(x: np.ndarray, edges: np.ndarray) -> np.ndarray:
    x = x[~np.isnan(x)]
    counts = np.histogram(x, bins=edges)[0].astype(float)
    return np.clip(counts / max(len(x), 1), EPS, None)


def psi(ref_share: np.ndarray, cur_share: np.ndarray) -> float:
    return float(np.sum((cur_share - ref_share) * np.log(cur_share / ref_share)))


class HealthMonitor:
    """Holds the training reference once; reports drift for the test period quickly."""

    def __init__(self, test_preds: pd.DataFrame | None = None, val_preds: pd.DataFrame | None = None):
        self.ref, self.cur = {}, {}
        for cls, spec in config.MACHINE_CLASSES.items():
            df = load_processed(cls)
            self.ref[cls] = {s: bin_edges(df.loc[df["split"] == "train", s].to_numpy()) for s in spec["sensors"]}
            self.ref[cls] = {s: (e, shares(df.loc[df["split"] == "train", s].to_numpy(), e))
                             for s, e in self.ref[cls].items()}
            self.cur[cls] = df.loc[df["split"] == "test", ["timestamp"] + spec["sensors"]].reset_index(drop=True)
        self.test_preds, self.val_preds = test_preds, val_preds
        start = min(c["timestamp"].min() for c in self.cur.values())
        self.start = start.normalize()

    def _week(self, ts: pd.Series) -> pd.Series:
        return ((ts - self.start).dt.days // 7).astype(int)

    def drift(self, inject: dict | None = None) -> dict:
        """PSI per class x sensor x week; `inject` = {"cls", "sensor", "pct", "from_week"}."""
        rows = []
        for cls, cur in self.cur.items():
            cur = cur.copy()
            if inject and inject.get("cls") == cls and inject.get("sensor") in cur.columns:
                wk = self._week(cur["timestamp"])
                m = wk >= int(inject.get("from_week", 0))
                cur.loc[m, inject["sensor"]] *= 1 + float(inject.get("pct", 0)) / 100
            cur["week"] = self._week(cur["timestamp"])
            for s, (edges, ref_share) in self.ref[cls].items():
                for wk, g in cur.groupby("week"):
                    v = psi(ref_share, shares(g[s].to_numpy(), edges))
                    rows.append({"machine_class": cls, "sensor": s, "week": int(wk),
                                 "week_start": (self.start + pd.Timedelta(days=7 * int(wk))).isoformat(),
                                 "readings": int(len(g)), "psi": round(v, 4), "status": psi_status(v)})
        table = pd.DataFrame(rows)
        worst = table.loc[table.groupby(["machine_class", "sensor"])["psi"].idxmax()]
        return {"weekly": table, "worst": worst.reset_index(drop=True)}

    def score_drift(self) -> pd.DataFrame:
        """PSI of the model's raw output: validation period (reference) vs each test week."""
        if self.test_preds is None or self.val_preds is None:
            return pd.DataFrame()
        rows = []
        for cls, v in self.val_preds.groupby("machine_class"):
            edges = bin_edges(v["predicted_risk"].to_numpy())
            ref = shares(v["predicted_risk"].to_numpy(), edges)
            t = self.test_preds[self.test_preds["machine_class"] == cls]
            for wk, g in t.groupby(self._week(t["timestamp"])):
                p = psi(ref, shares(g["predicted_risk"].to_numpy(), edges))
                rows.append({"machine_class": cls, "week": int(wk), "psi": round(p, 4), "status": psi_status(p)})
        return pd.DataFrame(rows)

    def weekly_performance(self) -> pd.DataFrame:
        if self.test_preds is None:
            return pd.DataFrame()
        t = self.test_preds.copy()
        t["week"] = self._week(t["timestamp"])
        rows = []
        for (cls, wk), g in t.groupby(["machine_class", "week"]):
            y, a = g["failure_label"], g["predicted_alert"]
            tp = int(((a == 1) & (y == 1)).sum())
            rows.append({
                "machine_class": cls, "week": int(wk), "readings": int(len(g)), "failures_ahead": int(y.sum()),
                "recall": tp / y.sum() if y.sum() else np.nan,
                "precision": tp / a.sum() if a.sum() else np.nan,
                "brier": brier_score_loss(y, g["calibrated_risk"]) if "calibrated_risk" in g else np.nan,
            })
        return pd.DataFrame(rows)
