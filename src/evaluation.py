"""
Evaluation: model-level and fusion-level.

MODEL-LEVEL FAIRNESS ("Level A")
Each specialised model is evaluated on its own machine class BEFORE fusion.
If a model misses failures here, no ranking strategy can recover them later.

Two views are reported:
  * Reading-level: every sensor reading is one prediction. Metrics: precision,
    recall, F1, FNR, PR-AUC, Brier score, calibration gap.
  * Event-level: every real failure is one event. An event is "caught" if the
    model raised at least one alert for that machine in the
    FAILURE_HORIZON_HOURS before the failure. This removes the bias of
    high-frequency machines having more readings (different data rates).

Accuracy is NOT reported as a headline metric: with ~10% positives, a model
that always predicts "healthy" would score ~90% accuracy and catch nothing.

FUSION-LEVEL FAIRNESS ("Level B")
After the fusion engine ranks machines into a top-k queue, measure per class
whether real failures reach the queue, and whether alerts get "buried".
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             f1_score, precision_recall_curve, precision_score, recall_score)

import config
from src.data_preprocessing import split_cutoffs

CLASS_COLORS = {"motor": "#2a6fdb", "pump": "#e07b00", "compressor": "#2e9e57"}


# ---------------------------------------------------------------------------
# Model-level metrics
# ---------------------------------------------------------------------------
def reading_level_metrics(preds):
    rows = []
    for (split, cls), g in preds.groupby(["split", "machine_class"]):
        y, p, a = g["failure_label"], g["predicted_risk"], g["predicted_alert"]
        tn, fp, fn, tp = confusion_matrix(y, a, labels=[0, 1]).ravel()
        rows.append({
            "split": split, "machine_class": cls,
            "model_name": g["model_name"].iloc[0],
            "readings": len(g), "positives": int(y.sum()),
            "prevalence": y.mean(),
            "alerts": int(a.sum()), "alert_rate": a.mean(),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision_score(y, a, zero_division=0),
            "recall": recall_score(y, a, zero_division=0),
            "fnr": fn / (tp + fn) if (tp + fn) else np.nan,
            "f1": f1_score(y, a, zero_division=0),
            "pr_auc": average_precision_score(y, p),
            "brier": brier_score_loss(y, p),
            # Positive gap = model says "riskier" than reality (over-confident).
            "mean_predicted_risk": p.mean(),
            "calibration_gap": p.mean() - y.mean(),
        })
    return pd.DataFrame(rows)


def _split_window(split):
    train_end, val_end = split_cutoffs()
    end = pd.Timestamp(config.SIM_START) + pd.Timedelta(days=config.SIM_DAYS)
    return (train_end, val_end) if split == "val" else (val_end, end)


def event_level_metrics(preds, failures):
    horizon = pd.Timedelta(hours=config.FAILURE_HORIZON_HOURS)
    event_rows = []
    for split in preds["split"].unique():
        lo, hi = _split_window(split)
        # Need the full horizon before the failure to be inside the split.
        events = failures[(failures["failure_time"] >= lo + horizon) &
                          (failures["failure_time"] < hi)]
        p_split = preds[preds["split"] == split]
        for _, ev in events.iterrows():
            w = p_split[(p_split["machine_id"] == ev["machine_id"]) &
                        (p_split["timestamp"] >= ev["failure_time"] - horizon) &
                        (p_split["timestamp"] < ev["failure_time"])]
            alerts = w[w["predicted_alert"] == 1]
            lead = round((ev["failure_time"] - alerts["timestamp"].min()).total_seconds() / 3600, 4) \
                if len(alerts) else np.nan
            event_rows.append({"split": split, "machine_class": ev["machine_class"],
                               "machine_id": ev["machine_id"],
                               "failure_time": ev["failure_time"],
                               "caught": int(len(alerts) > 0), "lead_time_h": lead})
    events_df = pd.DataFrame(event_rows)
    summary = (events_df.groupby(["split", "machine_class"])
               .agg(failure_events=("caught", "size"),
                    events_caught=("caught", "sum"),
                    median_lead_time_h=("lead_time_h", "median"))
               .reset_index())
    summary["event_recall"] = summary["events_caught"] / summary["failure_events"]
    return events_df, summary


def disparity_summary(metrics):
    """Gap between best and worst class for each fairness-relevant metric."""
    rows = []
    for split, g in metrics.groupby("split"):
        row = {"split": split}
        for m in ["recall", "fnr", "precision", "pr_auc", "event_recall"]:
            if m in g:
                row[f"{m}_max_minus_min"] = g[m].max() - g[m].min()
                # Worst = highest miss rate for fnr, lowest value for everything else.
                worst = g[m].idxmax() if m == "fnr" else g[m].idxmin()
                row[f"{m}_worst_class"] = g.loc[worst, "machine_class"]
        # Calibration: worst = largest absolute gap between predicted and actual rate.
        row["abs_calibration_gap_max"] = g["calibration_gap"].abs().max()
        row["calibration_worst_class"] = g.loc[g["calibration_gap"].abs().idxmax(), "machine_class"]
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Model-level figures
# ---------------------------------------------------------------------------
def plot_confusion_matrices(preds, split="test"):
    classes = list(config.MACHINE_CLASSES)
    fig, axes = plt.subplots(1, len(classes), figsize=(4.2 * len(classes), 3.8))
    for ax, cls in zip(axes, classes):
        g = preds[(preds["split"] == split) & (preds["machine_class"] == cls)]
        cm = confusion_matrix(g["failure_label"], g["predicted_alert"], labels=[0, 1])
        ax.imshow(cm, cmap="Blues")
        for (i, j), v in np.ndenumerate(cm):
            ax.text(j, i, f"{v}", ha="center", va="center",
                    color="white" if v > cm.max() / 2 else "black", fontsize=11)
        ax.set_xticks([0, 1], ["Healthy", "Alert"])
        ax.set_yticks([0, 1], ["Healthy", "Fails<24h"])
        ax.set_xlabel("Predicted"); ax.set_ylabel("Actual")
        ax.set_title(f"{cls} ({g['model_name'].iloc[0]})", fontsize=10)
    fig.suptitle(f"Confusion matrices — {split} set")
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / f"confusion_matrices_{split}.png", dpi=130)
    plt.close(fig)


def plot_pr_curves(preds, split="test"):
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for cls, g in preds[preds["split"] == split].groupby("machine_class"):
        prec, rec, _ = precision_recall_curve(g["failure_label"], g["predicted_risk"])
        ap = average_precision_score(g["failure_label"], g["predicted_risk"])
        ax.plot(rec, prec, color=CLASS_COLORS.get(cls), label=f"{cls} (PR-AUC {ap:.2f})")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title(f"Precision–recall by machine class — {split}")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / f"pr_curves_{split}.png", dpi=130)
    plt.close(fig)


def plot_reliability(preds, split="val"):
    """Reliability diagram: the motivation for calibration in the fusion engine."""
    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect calibration")
    for cls, g in preds[preds["split"] == split].groupby("machine_class"):
        frac_pos, mean_pred = calibration_curve(g["failure_label"], g["predicted_risk"],
                                                n_bins=10, strategy="quantile")
        ax.plot(mean_pred, frac_pos, "o-", color=CLASS_COLORS.get(cls), label=cls)
    ax.set_xlabel("Mean predicted risk"); ax.set_ylabel("Observed failure rate")
    ax.set_title(f"Reliability diagram (raw model scores) — {split}")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / f"reliability_raw_{split}.png", dpi=130)
    plt.close(fig)


def run_model_level_evaluation(preds, failures, save=True):
    metrics = reading_level_metrics(preds)
    events_df, event_summary = event_level_metrics(preds, failures)
    metrics = metrics.merge(event_summary, on=["split", "machine_class"], how="left")
    disparity = disparity_summary(metrics)

    if save:
        config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
        config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
        metrics.round(4).to_csv(config.METRICS_DIR / "model_metrics.csv", index=False)
        events_df.to_csv(config.METRICS_DIR / "failure_event_detection.csv", index=False)
        disparity.round(4).to_csv(config.METRICS_DIR / "model_level_disparity.csv", index=False)
        for split in ("val", "test"):
            plot_confusion_matrices(preds, split)
            plot_pr_curves(preds, split)
        plot_reliability(preds, "val")
        plot_reliability(preds, "test")
    return metrics, disparity


# ---------------------------------------------------------------------------
# Fusion-level fairness ("Level B")
# ---------------------------------------------------------------------------
# Unit of analysis = one machine in one review window. Ground truth `target`
# = machine fails within FAILURE_HORIZON_HOURS after the window ends.
#   captured  target=1 and in the top-k queue
#   missed    target=1 and not in the queue
#   buried    target=1, the machine's OWN model raised an alert, but the fusion
#             ranking left it out of the queue  <- the fairness failure mode
CLASSES = list(config.MACHINE_CLASSES)


def topk_class_coverage(ranked):
    """Per window x class counts for one strategy's ranked output."""
    r = ranked.assign(
        captured=(ranked["target"] == 1) & ranked["in_top_k"],
        buried=(ranked["target"] == 1) & (ranked["predicted_alert"] == 1) & ~ranked["in_top_k"],
        false_alarm=(ranked["target"] == 0) & ranked["in_top_k"],
    )
    g = r.groupby(["window", "machine_class"]).agg(
        targets=("target", "sum"), slots=("in_top_k", "sum"), captured=("captured", "sum"),
        buried=("buried", "sum"), false_alarms=("false_alarm", "sum"),
        promoted=("promoted", "sum"))
    full = pd.MultiIndex.from_product([sorted(r["window"].unique()), CLASSES],
                                      names=["window", "machine_class"])
    return g.reindex(full, fill_value=0).reset_index()


def _arrays(cov):
    """window x class arrays for fast bootstrapping."""
    piv = {c: cov.pivot(index="window", columns="machine_class", values=c)[CLASSES].to_numpy(float)
           for c in ["targets", "slots", "captured", "buried", "false_alarms"]}
    return piv


def _point_metrics(a, idx=None):
    t, s, c = (a[k] if idx is None else a[k][idx] for k in ("targets", "slots", "captured"))
    T, S, C = t.sum(0), s.sum(0), c.sum(0)
    sev = np.array([config.SEVERITY_WEIGHTS[k] for k in CLASSES])
    with np.errstate(invalid="ignore", divide="ignore"):
        class_recall = C / T
    return {
        "recall_at_k": C.sum() / T.sum(),
        "precision_at_k": C.sum() / S.sum(),
        "severity_weighted_recall": (C * sev).sum() / (T * sev).sum(),
        "class_recall": class_recall,
        "min_class_recall": np.nanmin(class_recall),
        "recall_disparity": np.nanmax(class_recall) - np.nanmin(class_recall),
    }


def _bootstrap(arrays_by_strategy, iters=config.BOOTSTRAP_ITERS):
    """Paired bootstrap over windows: same resampled windows for every strategy."""
    rng = np.random.default_rng(config.RANDOM_SEED)
    n = next(iter(arrays_by_strategy.values()))["targets"].shape[0]
    keys = ["recall_at_k", "precision_at_k", "severity_weighted_recall",
            "min_class_recall", "recall_disparity"]
    samples = {s: {k: [] for k in keys + ["class_recall"]} for s in arrays_by_strategy}
    for _ in range(iters):
        idx = rng.integers(0, n, n)
        for s, a in arrays_by_strategy.items():
            m = _point_metrics(a, idx)
            for k in keys + ["class_recall"]:
                samples[s][k].append(m[k])
    return {s: {k: np.array(v) for k, v in d.items()} for s, d in samples.items()}


def compare_strategies(ranked_by_strategy):
    """
    Returns
      comparison: one row per strategy, with 95% bootstrap CIs and the paired
                  difference vs the S1 baseline (CI excluding 0 = significant).
      per_class:  one row per strategy x class.
    """
    covs = {s: topk_class_coverage(r) for s, r in ranked_by_strategy.items()}
    arrays = {s: _arrays(c) for s, c in covs.items()}
    boot = _bootstrap(arrays)
    base = "S1_raw"

    rows, class_rows = [], []
    for s, a in arrays.items():
        pm = _point_metrics(a)
        row = {"strategy": s, "description": config.STRATEGIES[s]}
        for k in ["recall_at_k", "precision_at_k", "severity_weighted_recall",
                  "min_class_recall", "recall_disparity"]:
            lo, hi = np.percentile(boot[s][k], [2.5, 97.5])
            row[k], row[f"{k}_ci_low"], row[f"{k}_ci_high"] = pm[k], lo, hi
            if s != base:
                d = boot[s][k] - boot[base][k]
                row[f"{k}_vs_S1"] = pm[k] - _point_metrics(arrays[base])[k]
                row[f"{k}_vs_S1_ci_low"], row[f"{k}_vs_S1_ci_high"] = np.percentile(d, [2.5, 97.5])
        row["buried_total"] = int(a["buried"].sum())
        row["promoted_total"] = int(covs[s]["promoted"].sum())
        rows.append(row)

        total_slots, total_targets = a["slots"].sum(), a["targets"].sum()
        for j, cls in enumerate(CLASSES):
            cr = boot[s]["class_recall"][:, j]
            class_rows.append({
                "strategy": s, "machine_class": cls,
                "targets": int(a["targets"][:, j].sum()),
                "captured": int(a["captured"][:, j].sum()),
                "missed": int(a["targets"][:, j].sum() - a["captured"][:, j].sum()),
                "buried": int(a["buried"][:, j].sum()),
                "false_alarms_in_queue": int(a["false_alarms"][:, j].sum()),
                "recall_at_k": pm["class_recall"][j],
                "recall_ci_low": np.nanpercentile(cr, 2.5),
                "recall_ci_high": np.nanpercentile(cr, 97.5),
                # Paired difference vs S1 baseline: CI excluding 0 => real effect, not noise.
                "recall_vs_S1": pm["class_recall"][j] - _point_metrics(arrays[base])["class_recall"][j],
                "recall_vs_S1_ci_low": np.nanpercentile(cr - boot[base]["class_recall"][:, j], 2.5),
                "recall_vs_S1_ci_high": np.nanpercentile(cr - boot[base]["class_recall"][:, j], 97.5),
                "queue_share": a["slots"][:, j].sum() / total_slots,
                "failure_share": a["targets"][:, j].sum() / total_targets,
                "windows_with_zero_slots": int((a["slots"][:, j] == 0).sum()),
            })
    return pd.DataFrame(rows), pd.DataFrame(class_rows)


def k_sensitivity(snaps, ks=range(2, 17)):
    """Recall@k, precision@k and worst-class recall for every strategy across crew capacities."""
    from src.fusion_engine import rank_window
    rows = []
    groups = [g for _, g in snaps.groupby("window")]
    for s in config.STRATEGIES:
        for k in ks:
            ranked = pd.concat([rank_window(g, s, k) for g in groups], ignore_index=True)
            pm = _point_metrics(_arrays(topk_class_coverage(ranked)))
            rows.append({"strategy": s, "k": k, "recall_at_k": pm["recall_at_k"],
                         "precision_at_k": pm["precision_at_k"],
                         "min_class_recall": pm["min_class_recall"],
                         "recall_disparity": pm["recall_disparity"],
                         **{f"recall_{c}": v for c, v in zip(CLASSES, pm["class_recall"])}})
    return pd.DataFrame(rows)


STRATEGY_COLORS = {"S1_raw": "#9aa0a6", "S2_calibrated": "#5b8def",
                   "S3_risk_priority": "#1f3f8f", "S4_class_fair": "#d9534f"}


def plot_fusion_figures(test_preds, comparison, per_class, sensitivity):
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Reliability before vs after calibration (test set).
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, col, title in [(axes[0], "predicted_risk", "Raw model scores"),
                           (axes[1], "calibrated_risk", "After per-class isotonic calibration")]:
        ax.plot([0, 1], [0, 1], "k--", lw=1)
        for cls, g in test_preds.groupby("machine_class"):
            fp, mp = calibration_curve(g["failure_label"], g[col], n_bins=10, strategy="quantile")
            ax.plot(mp, fp, "o-", color=CLASS_COLORS[cls], label=cls)
        ax.set_title(title); ax.set_xlabel("Predicted risk"); ax.grid(alpha=0.3)
    axes[0].set_ylabel("Observed failure rate"); axes[1].legend()
    fig.suptitle("Calibration — test set")
    fig.tight_layout(); fig.savefig(config.FIGURES_DIR / "calibration_before_after.png", dpi=130)
    plt.close(fig)

    # 2. Per-class recall@k by strategy with 95% CIs.
    fig, ax = plt.subplots(figsize=(9, 4.5))
    strategies = list(config.STRATEGIES)
    width = 0.8 / len(strategies)
    x = np.arange(len(CLASSES))
    for i, s in enumerate(strategies):
        d = per_class[per_class["strategy"] == s].set_index("machine_class").loc[CLASSES]
        err = [d["recall_at_k"] - d["recall_ci_low"], d["recall_ci_high"] - d["recall_at_k"]]
        ax.bar(x + i * width - 0.4 + width / 2, d["recall_at_k"], width, yerr=err, capsize=3,
               color=STRATEGY_COLORS[s], label=s)
    ax.set_xticks(x, CLASSES); ax.set_ylim(0, 1.05); ax.set_ylabel(f"Recall@{config.TOP_K}")
    ax.set_title(f"Share of real failures that reach the top-{config.TOP_K} queue, by class")
    ax.legend(fontsize=8, ncol=2); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(config.FIGURES_DIR / "recall_at_k_by_class.png", dpi=130)
    plt.close(fig)

    # 3. Queue share vs failure share.
    fig, ax = plt.subplots(figsize=(9, 4.5))
    labels = ["Actual failures"] + strategies
    fail_share = per_class[per_class["strategy"] == "S1_raw"].set_index("machine_class").loc[CLASSES, "failure_share"]
    bottoms = np.zeros(len(labels))
    for cls in CLASSES:
        vals = [fail_share[cls]] + [per_class[(per_class["strategy"] == s) &
                                              (per_class["machine_class"] == cls)]["queue_share"].iloc[0]
                                    for s in strategies]
        ax.bar(labels, vals, bottom=bottoms, color=CLASS_COLORS[cls], label=cls)
        for xi, (v, b) in enumerate(zip(vals, bottoms)):
            ax.text(xi, b + v / 2, f"{v:.0%}", ha="center", va="center", color="white", fontsize=9)
        bottoms += vals
    ax.set_ylabel("Share"); ax.set_title("Who gets the maintenance slots? Queue share vs share of real failures")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1)); plt.setp(ax.get_xticklabels(), rotation=15)
    fig.tight_layout(); fig.savefig(config.FIGURES_DIR / "queue_share_vs_failures.png", dpi=130)
    plt.close(fig)

    # 4. Crew-capacity sensitivity.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    for s in strategies:
        d = sensitivity[sensitivity["strategy"] == s]
        axes[0].plot(d["k"], d["recall_at_k"], "o-", ms=3, color=STRATEGY_COLORS[s], label=s)
        axes[1].plot(d["k"], d["min_class_recall"], "o-", ms=3, color=STRATEGY_COLORS[s], label=s)
    for ax, t in zip(axes, ["Overall recall@k", "Worst-class recall@k"]):
        ax.axvline(config.TOP_K, color="k", ls=":", lw=1)
        ax.set_xlabel("Queue size k (crew capacity per 6 h)"); ax.set_title(t)
        ax.set_ylim(0, 1.02); ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(config.FIGURES_DIR / "k_sensitivity.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    from src.data_loader import load_failure_events
    from src.predict import load_predictions
    preds = pd.concat([load_predictions("val"), load_predictions("test")])
    m, d = run_model_level_evaluation(preds, load_failure_events())
    print(m.round(3).to_string(index=False))
    print(d.round(3).to_string(index=False))
