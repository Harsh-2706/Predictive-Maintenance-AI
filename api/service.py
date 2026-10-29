"""
Service layer for the web app: loads the trained models once and answers
questions about the plant. This is where the ML runs LIVE:

  * explain()   re-scores a machine with the real model, swapping one sensor
                at a time for its healthy value, to show what drives the risk.
  * what_if()   re-scores a machine with the real model after the user moves
                sensor sliders, then shows where it would land in the queue.
  * window()    ranks the fleet for any review window, strategy and crew size.

Everything reads the outputs of `python main.py` (models/, results/, data/).
"""
from __future__ import annotations

import json
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import average_precision_score

import config
from src import alert_manager, fusion_engine
from src.data_preprocessing import add_features, feature_columns, split_cutoffs
from src.train_models import load_model

CLASSES = list(config.MACHINE_CLASSES)
HEALTHY_MIN_HOURS_TO_FAILURE = 72      # "healthy" = more than 3 days before a failure
CACHE_PATH = config.MODELS_DIR / "web_cache.json"


def _iso(ts) -> str:
    return pd.Timestamp(ts).isoformat()


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe records (NaN becomes null)."""
    return df.round(4).astype(object).where(df.notna(), None).to_dict("records")


def _round(x, n=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


class PlantService:
    """Loads everything once; all methods are read-only and fast."""

    def __init__(self):
        missing = [p for p in [config.PREDICTIONS_DIR / "predictions_test.csv",
                               config.METRICS_DIR / "k_sensitivity.csv",
                               config.DATA_SIM_DIR / "failure_events.csv"]
                   + [config.MODELS_DIR / f"{c}_model.pkl" for c in CLASSES]
                   if not p.exists()]
        if missing:
            raise FileNotFoundError(
                "Pipeline outputs missing: " + ", ".join(str(m.relative_to(config.ROOT)) for m in missing)
                + ". Run `python main.py` first.")

        self.bundles = {c: load_model(c) for c in CLASSES}
        self.val = pd.read_csv(config.PREDICTIONS_DIR / "predictions_val.csv", parse_dates=["timestamp"])
        self.test = pd.read_csv(config.PREDICTIONS_DIR / "predictions_test.csv", parse_dates=["timestamp"])
        cal_path = fusion_engine.CALIBRATORS_PATH
        self.calibrators = (joblib.load(cal_path) if cal_path.exists()
                            else fusion_engine.fit_calibrators(self.val))
        self.test = fusion_engine.apply_calibration(self.test, self.calibrators)
        self.val = fusion_engine.apply_calibration(self.val, self.calibrators)
        self.snaps = fusion_engine.add_priority_components(
            fusion_engine.apply_calibration(alert_manager.build_windows(self.test), self.calibrators))
        self.windows = (self.snaps[["window", "window_end"]].drop_duplicates()
                        .sort_values("window").reset_index(drop=True))
        self.failures = pd.read_csv(config.DATA_SIM_DIR / "failure_events.csv", parse_dates=["failure_time"])
        self.raw = {c: pd.read_csv(config.DATA_SIM_DIR / f"{c}_raw.csv", parse_dates=["timestamp"])
                    for c in CLASSES}
        self.machine_class = (pd.concat(self.raw.values())[["machine_id", "machine_class"]]
                              .drop_duplicates().set_index("machine_id")["machine_class"].to_dict())
        self.metrics = {name: pd.read_csv(config.METRICS_DIR / f"{name}.csv") for name in
                        ["model_metrics", "calibration_report", "strategy_comparison",
                         "strategy_per_class", "k_sensitivity", "alert_volume_by_class"]}
        self._features: dict[str, pd.DataFrame] = {}
        self.cache = self._load_or_build_cache()

    # ------------------------------------------------------------------ features
    def features_for(self, machine_id: str) -> pd.DataFrame:
        """Model input features for one machine, computed from its raw readings (cached)."""
        if machine_id not in self._features:
            cls = self.machine_class[machine_id]
            raw = self.raw[cls]
            f = add_features(raw[raw["machine_id"] == machine_id].copy(), config.MACHINE_CLASSES[cls]["sensors"])
            self._features[machine_id] = f.set_index("timestamp").sort_index()
        return self._features[machine_id]

    def _score(self, cls: str, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        b = self.bundles[cls]
        raw = b["model"].predict_proba(X[b["features"]])[:, 1]
        return raw, self.calibrators[cls].predict(raw)

    def _sensor_cols(self, cls, sensor):
        return [c for c in feature_columns(config.MACHINE_CLASSES[cls]["sensors"])
                if c == sensor or c.startswith(f"{sensor}_")]

    # ------------------------------------------------------------------ cache
    def _load_or_build_cache(self) -> dict:
        """Healthy baselines and sensor importance — computed once, then reused."""
        stamp = {c: self.bundles[c]["trained_at"] for c in CLASSES}
        if CACHE_PATH.exists():
            cached = json.loads(CACHE_PATH.read_text())
            if cached.get("models_trained_at") == stamp:
                return cached
        train_end, val_end = split_cutoffs()
        rng = np.random.default_rng(config.RANDOM_SEED)
        out = {"models_trained_at": stamp, "healthy": {}, "importance": {}}
        for cls in CLASSES:
            sensors = config.MACHINE_CLASSES[cls]["sensors"]
            machines = sorted(self.raw[cls]["machine_id"].unique())[:8]
            feats = pd.concat([self.features_for(m).reset_index() for m in machines])
            cols = feature_columns(sensors)

            healthy = feats[(feats["timestamp"] < train_end) &
                            (feats["time_to_failure_h"] > HEALTHY_MIN_HOURS_TO_FAILURE)]
            out["healthy"][cls] = {
                "median": healthy[cols].median().to_dict(),
                "std": healthy[sensors].std().to_dict(),
            }

            # Grouped permutation importance on validation-period rows:
            # shuffle ALL features of one sensor together, measure the drop in PR-AUC.
            val = feats[(feats["timestamp"] >= train_end) & (feats["timestamp"] < val_end)]
            val = val.sample(min(len(val), 6000), random_state=config.RANDOM_SEED)
            y = val["failure_label"].to_numpy()
            base = average_precision_score(y, self._score(cls, val[cols])[0])
            imp = {}
            for s in sensors + ["minutes_since_last"]:
                group = self._sensor_cols(cls, s) if s != "minutes_since_last" else [s]
                drops = []
                for _ in range(3):
                    shuffled = val[cols].copy()
                    perm = rng.permutation(len(shuffled))
                    shuffled[group] = shuffled[group].to_numpy()[perm]
                    drops.append(base - average_precision_score(y, self._score(cls, shuffled)[0]))
                imp[s] = float(np.mean(drops))
            out["importance"][cls] = {"baseline_pr_auc": base, "drop": imp}
        CACHE_PATH.write_text(json.dumps(out, indent=1, default=float))
        return out

    # ------------------------------------------------------------------ ranking
    @lru_cache(maxsize=64)
    def ranked(self, strategy: str, k: int) -> pd.DataFrame:
        if strategy not in config.STRATEGIES:
            raise ValueError(f"Unknown strategy {strategy}")
        if not 1 <= k <= 30:
            raise ValueError("k must be between 1 and 30")
        return fusion_engine.rank_all_windows(self.snaps, strategy, k)

    def fleet(self) -> dict:
        machines = [{"id": m, "cls": self.machine_class[m]} for m in sorted(self.machine_class)]
        return {
            "classes": [{"id": c, "count": config.MACHINE_CLASSES[c]["n_machines"],
                         "model": config.MODEL_CHOICE[c],
                         "sample_every_min": config.MACHINE_CLASSES[c]["sample_every_min"],
                         "severity": config.SEVERITY_WEIGHTS[c],
                         "sensors": config.MACHINE_CLASSES[c]["sensors"]} for c in CLASSES],
            "machines": machines,
            "windows": [{"window": int(r.window), "end": _iso(r.window_end)} for r in self.windows.itertuples()],
            "strategies": [{"id": s, "label": l} for s, l in config.STRATEGIES.items()],
            "default_strategy": "S3_risk_priority",
            "default_k": config.TOP_K,
            "review_window_hours": config.REVIEW_WINDOW_HOURS,
            "horizon_hours": config.FAILURE_HORIZON_HOURS,
        }

    def window(self, w: int, strategy: str, k: int) -> dict:
        r = self.ranked(strategy, k)
        win = r[r["window"] == w]
        if win.empty:
            raise KeyError(f"No review window {w}")
        end = win["window_end"].iloc[0]
        reporting = set(win["machine_id"])
        machines = []
        for row in win.itertuples():
            machines.append({
                "id": row.machine_id, "cls": row.machine_class, "rank": int(row.rank),
                "in_queue": bool(row.in_top_k), "status": row.alert_status or None,
                "raw": _round(row.predicted_risk), "risk": _round(row.calibrated_risk),
                "severity": _round(row.severity, 2), "freshness": _round(row.freshness, 3),
                "age_min": _round(row.age_min, 1), "priority": _round(row.priority_score),
                "promoted": bool(row.promoted), "fails_24h": int(row.target),
            })
        for m in sorted(set(self.machine_class) - reporting):
            machines.append({"id": m, "cls": self.machine_class[m], "rank": None, "in_queue": False,
                             "status": "offline", "raw": None, "risk": None, "priority": None,
                             "fails_24h": 0})
        queue = sorted([m for m in machines if m["in_queue"]], key=lambda m: m["rank"])
        failing = [m for m in machines if m["fails_24h"]]
        return {
            "window": w, "end": _iso(end), "strategy": strategy, "k": k,
            "machines": machines, "queue": queue,
            "summary": {
                "reporting": len(reporting), "high_risk": sum(1 for m in machines if (m["risk"] or 0) >= 0.5),
                "new_alerts": sum(1 for m in queue if m["status"] == "new"),
                "failing_24h": len(failing), "caught": sum(1 for m in queue if m["fails_24h"]),
            },
        }

    # ------------------------------------------------------------------ machine
    def _snapshot(self, machine_id: str, w: int):
        s = self.snaps[(self.snaps["machine_id"] == machine_id) & (self.snaps["window"] == w)]
        if s.empty:
            raise KeyError(f"{machine_id} did not report in window {w}")
        return s.iloc[0]

    def machine(self, machine_id: str, strategy: str, k: int) -> dict:
        if machine_id not in self.machine_class:
            raise KeyError(f"Unknown machine {machine_id}")
        cls = self.machine_class[machine_id]
        r = self.ranked(strategy, k)
        mr = r[r["machine_id"] == machine_id].sort_values("window")
        start, end = self.test["timestamp"].min(), self.test["timestamp"].max()

        raw = self.raw[cls]
        sd = raw[(raw["machine_id"] == machine_id) & (raw["timestamp"] >= start)].set_index("timestamp")
        sensors = config.MACHINE_CLASSES[cls]["sensors"]
        hourly = sd[sensors].resample("1h").mean().dropna(how="all").reset_index()
        healthy = self.cache["healthy"][cls]
        fails = self.failures[(self.failures["machine_id"] == machine_id) &
                              (self.failures["failure_time"].between(start, end))]
        return {
            "id": machine_id, "cls": cls, "model": config.MODEL_CHOICE[cls],
            "severity": config.SEVERITY_WEIGHTS[cls],
            "sample_every_min": config.MACHINE_CLASSES[cls]["sample_every_min"],
            "timeline": [{"window": int(x.window), "end": _iso(x.window_end), "raw": _round(x.predicted_risk),
                          "risk": _round(x.calibrated_risk), "priority": _round(x.priority_score),
                          "rank": int(x.rank), "in_queue": bool(x.in_top_k)} for x in mr.itertuples()],
            "failures": [_iso(t) for t in fails["failure_time"]],
            "sensors": [{"name": s, "normal": _round(healthy["median"][s], 3),
                         "points": [[_iso(t), _round(v, 3)] for t, v in zip(hourly["timestamp"], hourly[s])]}
                        for s in sensors],
        }

    def explain(self, machine_id: str, w: int) -> dict:
        """Live: how much of this machine's risk comes from each sensor."""
        cls = self.machine_class[machine_id]
        snap = self._snapshot(machine_id, w)
        X = self.features_for(machine_id).loc[[snap["timestamp"]]]
        raw0, cal0 = self._score(cls, X)
        healthy = self.cache["healthy"][cls]["median"]
        drivers = []
        for s in config.MACHINE_CLASSES[cls]["sensors"]:
            Xs = X.copy()
            for c in self._sensor_cols(cls, s):
                Xs[c] = healthy[c]
            _, cal_s = self._score(cls, Xs)
            drivers.append({"sensor": s, "value": _round(X[s].iloc[0], 3), "normal": _round(healthy[s], 3),
                            "trend": _round(X[f"{s}_trend"].iloc[0], 3),
                            "risk_if_normal": _round(cal_s[0]), "contribution": _round(cal0[0] - cal_s[0])})
        drivers.sort(key=lambda d: -d["contribution"])
        return {"machine": machine_id, "window": w, "reading_time": _iso(snap["timestamp"]),
                "raw": _round(raw0[0]), "risk": _round(cal0[0]), "drivers": drivers}

    def what_if(self, machine_id: str, w: int, deltas: dict[str, float], strategy: str, k: int) -> dict:
        """
        Live: shift sensors by `deltas` (physical units) as if the change built up
        over the last ~2 hours, re-score with the real model, and re-rank the window.
        Short-window means move fully, the 6 h mean half-way, so the trend reflects it.
        """
        cls = self.machine_class[machine_id]
        sensors = config.MACHINE_CLASSES[cls]["sensors"]
        unknown = set(deltas) - set(sensors)
        if unknown:
            raise ValueError(f"{machine_id} has no sensor(s) {sorted(unknown)}")
        snap = self._snapshot(machine_id, w)
        X = self.features_for(machine_id).loc[[snap["timestamp"]]].copy()
        short, long = config.ROLLING_WINDOWS[0], config.ROLLING_WINDOWS[-1]
        for s, d in deltas.items():
            X[s] += d
            X[f"{s}_mean_{short}"] += d
            X[f"{s}_mean_{long}"] += d / 2
            X[f"{s}_trend"] = X[f"{s}_mean_{short}"] - X[f"{s}_mean_{long}"]
        raw, cal = self._score(cls, X)
        priority = float(cal[0]) * config.SEVERITY_WEIGHTS[cls] * float(snap["freshness"])

        win = self.snaps[self.snaps["window"] == w].copy()
        m = win["machine_id"] == machine_id
        win.loc[m, ["predicted_risk", "calibrated_risk"]] = [raw[0], cal[0]]
        win = fusion_engine.add_priority_components(win)
        ranked = fusion_engine.rank_window(win, strategy, k)
        new_rank = int(ranked.loc[ranked["machine_id"] == machine_id, "rank"].iloc[0])
        before = self.ranked(strategy, k)
        old_rank = int(before[(before["window"] == w) & (before["machine_id"] == machine_id)]["rank"].iloc[0])
        return {"machine": machine_id, "window": w, "raw": _round(raw[0]), "risk": _round(cal[0]),
                "priority": _round(priority), "rank": new_rank, "rank_before": old_rank,
                "in_queue": new_rank <= k, "k": k}

    def slider_ranges(self, machine_id: str) -> list[dict]:
        cls = self.machine_class[machine_id]
        std = self.cache["healthy"][cls]["std"]
        return [{"sensor": s, "step": _round(std[s] / 10, 4), "min": _round(-4 * std[s], 3),
                 "max": _round(4 * std[s], 3)} for s in config.MACHINE_CLASSES[cls]["sensors"]]

    # ------------------------------------------------------------------ analysis
    def calibration(self) -> dict:
        out = {}
        for cls, g in self.test.groupby("machine_class"):
            curves = {}
            for col, key in [("predicted_risk", "raw"), ("calibrated_risk", "calibrated")]:
                fp, mp = calibration_curve(g["failure_label"], g[col], n_bins=10, strategy="quantile")
                curves[key] = [[_round(a), _round(b)] for a, b in zip(mp, fp)]
            # Real failure rate for raw scores between 0.7 and 0.9 — the headline comparison.
            band = g[g["predicted_risk"].between(0.7, 0.9)]
            curves["observed_at_0_8"] = _round(band["failure_label"].mean())
            out[cls] = curves
        rep = self.metrics["calibration_report"].set_index("machine_class")
        return {"curves": out, "report": _records(rep.reset_index())}

    def fairness(self) -> dict:
        return {
            "sensitivity": _records(self.metrics["k_sensitivity"]),
            "per_class": _records(self.metrics["strategy_per_class"]),
            "comparison": _records(self.metrics["strategy_comparison"]),
            "k_default": config.TOP_K,
        }

    def models(self) -> dict:
        mm = self.metrics["model_metrics"]
        test = mm[mm["split"] == "test"]
        cards = []
        for row in test.itertuples():
            imp = self.cache["importance"][row.machine_class]
            cards.append({
                "cls": row.machine_class, "model": row.model_name, "readings": int(row.readings),
                "prevalence": _round(row.prevalence), "precision": _round(row.precision),
                "recall": _round(row.recall), "pr_auc": _round(row.pr_auc), "brier": _round(row.brier),
                "confusion": {"tp": int(row.tp), "fp": int(row.fp), "fn": int(row.fn), "tn": int(row.tn)},
                "importance": sorted([{"sensor": s, "drop": _round(v)} for s, v in imp["drop"].items()],
                                     key=lambda d: -d["drop"]),
                "features": len(self.bundles[row.machine_class]["features"]),
            })
        order = {c: i for i, c in enumerate(CLASSES)}
        return {"cards": sorted(cards, key=lambda c: order[c["cls"]]),
                "volume": _records(self.metrics["alert_volume_by_class"])}

    def story(self) -> dict:
        cal = self.metrics["calibration_report"].set_index("machine_class")
        pc = self.metrics["strategy_per_class"].set_index(["strategy", "machine_class"])
        comp = self.metrics["strategy_comparison"].set_index("strategy")
        sens = self.metrics["k_sensitivity"].set_index(["strategy", "k"])
        g = lambda s, c, col: _round(pc.loc[(s, c), col])
        return {
            "machines": len(self.machine_class), "classes": len(CLASSES),
            "windows": len(self.windows),
            "failures_in_test": int(self.failures["failure_time"].between(
                self.test["timestamp"].min(), self.test["timestamp"].max()).sum()),
            "k": config.TOP_K, "review_window_hours": config.REVIEW_WINDOW_HOURS,
            "calibration": _records(cal.reset_index()),
            "compressor": {s: {"recall": g(s, "compressor", "recall_at_k"),
                               "delta": g(s, "compressor", "recall_vs_S1"),
                               "ci_low": g(s, "compressor", "recall_vs_S1_ci_low"),
                               "ci_high": g(s, "compressor", "recall_vs_S1_ci_high"),
                               "queue_share": g(s, "compressor", "queue_share"),
                               "failure_share": g(s, "compressor", "failure_share")}
                           for s in config.STRATEGIES},
            "overall": {s: {"recall": _round(comp.loc[s, "recall_at_k"]),
                            "precision": _round(comp.loc[s, "precision_at_k"])} for s in config.STRATEGIES},
            "tight_crew": {s: {c: _round(sens.loc[(s, 4), f"recall_{c}"]) for c in CLASSES}
                           for s in config.STRATEGIES},
        }
