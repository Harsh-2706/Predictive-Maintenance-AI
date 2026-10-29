"""
Fusion engine — the core R&D component.

PROBLEM
Three models (Random Forest, Gradient Boosting, Logistic Regression) produce
scores on three machine classes. Model evaluation shows these scores are NOT on the same
scale: a raw score of 0.8 means a very different real failure rate for a
compressor than for a motor (results/figures/reliability_raw_val.png).
Ranking raw scores across classes is therefore comparing unlike units.

DESIGN (four strategies, evaluated on the same test windows)
  S1_raw            priority = raw model score                         (baseline)
  S2_calibrated     priority = calibrated risk                         (fixes scale)
  S3_risk_priority  priority = calibrated risk x severity x freshness  (adds consequence + data age)
  S4_class_fair     S3, plus a class-coverage safeguard                (fairness policy)

Each strategy adds ONE idea, so the comparison is an ablation: any change in
results can be attributed to that idea.

Calibration
  Per-class isotonic regression, fitted on VALIDATION predictions only and
  applied to test. Isotonic is non-parametric and monotonic: it keeps each
  model's ranking within its class and only fixes what the numbers mean.
  We do NOT multiply by a separate "confidence" term — calibration already
  encodes how trustworthy a score is; a second penalty would double-count.

Severity
  config.SEVERITY_WEIGHTS — relative consequence of an unplanned failure.
  Turns probability into expected-consequence priority (no longer a probability).

Freshness
  0.5 ** (age_min / FRESHNESS_HALF_LIFE_MIN): stale data counts for less,
  so a machine that stopped reporting is not ranked on old evidence.

Class-coverage safeguard (S4)
  If a class has no machine in the top-k but has a machine with calibrated
  risk >= MIN_ELIGIBLE_RISK, its best machine replaces the lowest-ranked
  machine of the most represented class. It is a human-review policy that
  guarantees visibility; it does not claim the models are fairer.
"""
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss

import config
from src import alert_manager

CALIBRATORS_PATH = config.MODELS_DIR / "calibrators.pkl"


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def fit_calibrators(val_preds: pd.DataFrame) -> dict:
    """Per-class isotonic calibrator, fitted on validation predictions only."""
    if (val_preds["split"] != "val").any():
        raise ValueError("Calibrators must be fitted on validation predictions only.")
    calibrators = {}
    for cls, g in val_preds.groupby("machine_class"):
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        iso.fit(g["predicted_risk"], g["failure_label"])
        calibrators[cls] = iso
    return calibrators


def apply_calibration(df: pd.DataFrame, calibrators: dict) -> pd.DataFrame:
    df = df.copy()
    df["calibrated_risk"] = np.nan
    for cls, iso in calibrators.items():
        m = df["machine_class"] == cls
        df.loc[m, "calibrated_risk"] = iso.predict(df.loc[m, "predicted_risk"])
    if df["calibrated_risk"].isna().any():
        missing = df.loc[df["calibrated_risk"].isna(), "machine_class"].unique()
        raise ValueError(f"No calibrator for classes: {missing}")
    return df


def calibration_report(test_preds: pd.DataFrame) -> pd.DataFrame:
    """Brier score and mean-risk gap before vs after calibration, per class (test)."""
    rows = []
    for cls, g in test_preds.groupby("machine_class"):
        y = g["failure_label"]
        rows.append({
            "machine_class": cls,
            "actual_rate": y.mean(),
            "mean_raw_risk": g["predicted_risk"].mean(),
            "mean_calibrated_risk": g["calibrated_risk"].mean(),
            "brier_raw": brier_score_loss(y, g["predicted_risk"]),
            "brier_calibrated": brier_score_loss(y, g["calibrated_risk"]),
        })
    out = pd.DataFrame(rows)
    out["brier_improvement_pct"] = 100 * (1 - out["brier_calibrated"] / out["brier_raw"])
    return out


# ---------------------------------------------------------------------------
# Priority scores
# ---------------------------------------------------------------------------
def freshness_factor(age_min):
    """Data-freshness factor in (0, 1]: halves every FRESHNESS_HALF_LIFE_MIN minutes."""
    return 0.5 ** (np.asarray(age_min, dtype=float) / config.FRESHNESS_HALF_LIFE_MIN)


def add_priority_components(snaps: pd.DataFrame) -> pd.DataFrame:
    snaps = snaps.copy()
    snaps["severity"] = snaps["machine_class"].map(config.SEVERITY_WEIGHTS)
    snaps["freshness"] = freshness_factor(snaps["age_min"])
    snaps["score_S1_raw"] = snaps["predicted_risk"]
    snaps["score_S2_calibrated"] = snaps["calibrated_risk"]
    snaps["score_S3_risk_priority"] = snaps["calibrated_risk"] * snaps["severity"] * snaps["freshness"]
    snaps["score_S4_class_fair"] = snaps["score_S3_risk_priority"]
    return snaps


def _explain(row, strategy):
    if strategy == "S1_raw":
        return f"raw {row.predicted_risk:.2f}"
    if strategy == "S2_calibrated":
        return f"calibrated {row.calibrated_risk:.2f} (raw {row.predicted_risk:.2f})"
    text = (f"calibrated {row.calibrated_risk:.2f} x severity {row.severity:.1f} "
            f"x freshness {row.freshness:.2f}")
    return text


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def _apply_class_safeguard(ranked: pd.DataFrame, k: int) -> pd.DataFrame:
    """S4: guarantee MIN_SLOTS_PER_CLASS per class among eligible machines."""
    ranked = ranked.copy()
    ranked["promoted"] = False
    top = ranked.index[:k].tolist()
    rest = ranked.index[k:].tolist()

    for cls in config.MACHINE_CLASSES:
        while (ranked.loc[top, "machine_class"] == cls).sum() < config.MIN_SLOTS_PER_CLASS:
            candidates = [i for i in rest
                          if ranked.at[i, "machine_class"] == cls
                          and ranked.at[i, "calibrated_risk"] >= config.MIN_ELIGIBLE_RISK]
            if not candidates:
                break
            counts = ranked.loc[top, "machine_class"].value_counts()
            donors = [c for c in counts.index if counts[c] > config.MIN_SLOTS_PER_CLASS]
            if not donors:
                break
            donor = counts[donors].idxmax()
            # Lowest-ranked, non-promoted member of the donor class leaves the queue.
            out_idx = [i for i in top if ranked.at[i, "machine_class"] == donor
                       and not ranked.at[i, "promoted"]][-1]
            in_idx = candidates[0]  # rest is already sorted by score
            top.remove(out_idx); rest.insert(0, out_idx)
            rest.remove(in_idx); top.append(in_idx)
            ranked.at[in_idx, "promoted"] = True

    order = (ranked.loc[top].sort_values("priority_score", ascending=False).index.tolist()
             + ranked.loc[rest].sort_values("priority_score", ascending=False).index.tolist())
    return ranked.loc[order]


def rank_window(window_snaps: pd.DataFrame, strategy: str, k: int = config.TOP_K) -> pd.DataFrame:
    """Rank one review window. Ties broken by raw score, then machine_id (deterministic)."""
    if strategy not in config.STRATEGIES:
        raise ValueError(f"Unknown strategy {strategy}")
    df = window_snaps.copy()
    df["priority_score"] = df[f"score_{strategy}"]
    df = df.sort_values(["priority_score", "predicted_risk", "machine_id"],
                        ascending=[False, False, True])
    if strategy == "S4_class_fair":
        df = _apply_class_safeguard(df, k)
    else:
        df["promoted"] = False
    df["rank"] = np.arange(1, len(df) + 1)
    df["in_top_k"] = df["rank"] <= k
    df["strategy"] = strategy
    df["explanation"] = [_explain(r, strategy) + (" | promoted: class coverage" if r.promoted else "")
                         for r in df.itertuples()]
    return df


def rank_all_windows(snaps: pd.DataFrame, strategy: str, k: int = config.TOP_K) -> pd.DataFrame:
    ranked = pd.concat([rank_window(g, strategy, k) for _, g in snaps.groupby("window")],
                       ignore_index=True)
    return alert_manager.mark_new_vs_ongoing(ranked)


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------
QUEUE_COLUMNS = ["window", "window_end", "rank", "in_top_k", "alert_status", "machine_id",
                 "machine_class", "priority_score", "predicted_risk", "calibrated_risk",
                 "severity", "freshness", "age_min", "promoted", "explanation",
                 "predicted_alert", "target", "strategy"]


def prepare_test_snapshots():
    """Load predictions, calibrate on val, build scored test snapshots."""
    from src.predict import load_predictions
    val, test = load_predictions("val"), load_predictions("test")
    calibrators = fit_calibrators(val)
    joblib.dump(calibrators, CALIBRATORS_PATH)
    test = apply_calibration(test, calibrators)
    snaps = add_priority_components(apply_calibration(alert_manager.build_windows(test),
                                                      calibrators))
    return val, test, snaps, calibrators


def run_fusion_experiment(save=True):
    from src import evaluation

    val, test, snaps, _ = prepare_test_snapshots()
    calib = calibration_report(test)
    volume = alert_manager.alert_volume_by_class(test, snaps)

    ranked = {s: rank_all_windows(snaps, s) for s in config.STRATEGIES}
    comparison, per_class = evaluation.compare_strategies(ranked)
    sensitivity = evaluation.k_sensitivity(snaps)

    if save:
        config.PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        for s, r in ranked.items():
            r[QUEUE_COLUMNS].to_csv(config.PREDICTIONS_DIR / f"ranked_alerts_{s}.csv", index=False)
        calib.round(4).to_csv(config.METRICS_DIR / "calibration_report.csv", index=False)
        volume.round(4).to_csv(config.METRICS_DIR / "alert_volume_by_class.csv", index=False)
        comparison.round(4).to_csv(config.METRICS_DIR / "strategy_comparison.csv", index=False)
        per_class.round(4).to_csv(config.METRICS_DIR / "strategy_per_class.csv", index=False)
        sensitivity.round(4).to_csv(config.METRICS_DIR / "k_sensitivity.csv", index=False)
        evaluation.plot_fusion_figures(test, comparison, per_class, sensitivity)
        meta = {"top_k": config.TOP_K, "review_window_hours": config.REVIEW_WINDOW_HOURS,
                "windows": int(snaps["window"].nunique()),
                "machines": int(snaps["machine_id"].nunique()),
                "severity_weights": config.SEVERITY_WEIGHTS,
                "min_slots_per_class": config.MIN_SLOTS_PER_CLASS,
                "min_eligible_risk": config.MIN_ELIGIBLE_RISK}
        (config.METRICS_DIR / "fusion_run.json").write_text(json.dumps(meta, indent=2))

    return {"calibration": calib, "volume": volume, "comparison": comparison,
            "per_class": per_class, "sensitivity": sensitivity, "ranked": ranked}
