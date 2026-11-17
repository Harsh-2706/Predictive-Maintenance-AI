"""
End-to-end pipeline entry point.

    python main.py                 # full pipeline (all stages)
    python main.py --stage simulate
    python main.py --stage preprocess
    python main.py --stage train
    python main.py --stage predict
    python main.py --stage evaluate
    python main.py --stage fusion
    python main.py --stage rul        # remaining-useful-life models
    python main.py --stage baselines  # AI vs alarm limits / fixed schedule / run-to-failure
    python main.py --stage health     # data drift + weekly model performance
    python main.py --stage models  # simulate..evaluate only (skip fusion and later)
"""
import argparse
import time

import pandas as pd

import config
from src import data_loader, data_preprocessing, data_simulator, evaluation, predict, train_models

MODEL_STAGES = ["simulate", "preprocess", "train", "predict", "evaluate"]
ALL_STAGES = MODEL_STAGES + ["fusion", "rul", "baselines", "health"]


def stage_simulate():
    frames, failures = data_simulator.simulate_all()
    print(data_simulator.summarise(frames, failures).to_string(index=False))


def stage_preprocess():
    for cls, df in data_loader.load_all().items():
        out = data_preprocessing.preprocess_class(df, cls)
        counts = out["split"].value_counts().to_dict()
        print(f"  {cls:<11} features={len(data_preprocessing.feature_columns(config.MACHINE_CLASSES[cls]['sensors']))} "
              f"splits={counts}")


def stage_train():
    for cls, b in train_models.train_all().items():
        print(f"  {cls:<11} {b['model_name']:<20} train_rows={b['train_rows']} "
              f"pos_rate={b['train_positive_rate']:.3f}")


def stage_predict():
    p = predict.predict_all()
    print(p.groupby(["split", "machine_class"]).size().to_string())


def stage_evaluate():
    preds = pd.concat([predict.load_predictions("val"), predict.load_predictions("test")])
    metrics, disparity = evaluation.run_model_level_evaluation(preds, data_loader.load_failure_events())
    cols = ["split", "machine_class", "model_name", "precision", "recall", "fnr", "f1",
            "pr_auc", "brier", "calibration_gap", "event_recall", "median_lead_time_h"]
    print(metrics[cols].round(3).to_string(index=False))
    print("\nDisparity (max - min across classes):")
    print(disparity.round(3).to_string(index=False))


def stage_fusion():
    from src import fusion_engine
    out = fusion_engine.run_fusion_experiment()
    print("Calibration (test set):")
    print(out["calibration"].round(3).to_string(index=False))
    print("\nAlert volume (data-rate effect):")
    print(out["volume"].round(3).to_string(index=False))
    cols = ["strategy", "recall_at_k", "recall_at_k_ci_low", "recall_at_k_ci_high", "precision_at_k",
            "severity_weighted_recall", "min_class_recall", "recall_disparity", "buried_total",
            "promoted_total"]
    print(f"\nStrategy comparison (top-{config.TOP_K} per {config.REVIEW_WINDOW_HOURS} h window, test set):")
    print(out["comparison"][cols].round(3).to_string(index=False))
    print("\nPer class:")
    print(out["per_class"].round(3).to_string(index=False))


def stage_rul():
    from src import rul
    _, metrics = rul.run_rul()
    print("Remaining useful life (test set, hours; target capped at "
          f"{rul.RUL_CAP_H:g} h):")
    print(metrics.round(2).to_string(index=False))


def stage_baselines():
    from src import baselines
    out = baselines.run_baselines()
    cols = ["approach", "inspections", "recall_at_k", "precision_at_k", "events_caught",
            "failure_events", "median_warning_h", "ai_recall_gain", "ai_recall_gain_ci_low",
            "ai_recall_gain_ci_high"]
    print(f"Same crew (top-{config.TOP_K} per {config.REVIEW_WINDOW_HOURS} h), test period:")
    print(out["comparison"][cols].round(3).to_string(index=False))
    sv = baselines.savings(out["comparison"])
    print("\nMonthly cost with the example costs (INR; edit them in the web app):")
    print(sv["rows"][["approach", "breakdowns", "total", "saving_vs_reactive", "saving_pct"]]
          .round(0).to_string(index=False))


def stage_health():
    from src import fusion_engine, model_health, predict
    import joblib
    cal = joblib.load(fusion_engine.CALIBRATORS_PATH)
    test = fusion_engine.apply_calibration(predict.load_predictions("test"), cal)
    mon = model_health.HealthMonitor(test, predict.load_predictions("val"))
    drift = mon.drift()
    drift["weekly"].to_csv(config.METRICS_DIR / "drift_psi.csv", index=False)
    mon.weekly_performance().round(4).to_csv(config.METRICS_DIR / "weekly_performance.csv", index=False)
    print("Worst weekly PSI per sensor (training period vs each test week):")
    print(drift["worst"][["machine_class", "sensor", "week", "psi", "status"]].to_string(index=False))


STAGES = {
    "simulate": stage_simulate, "preprocess": stage_preprocess, "train": stage_train,
    "predict": stage_predict, "evaluate": stage_evaluate, "fusion": stage_fusion,
    "rul": stage_rul, "baselines": stage_baselines, "health": stage_health,
}


def main():
    parser = argparse.ArgumentParser(description="Multi-machine predictive maintenance pipeline")
    parser.add_argument("--stage", choices=list(STAGES) + ["models", "all"], default="all")
    args = parser.parse_args()

    if args.stage == "all":
        stages = ALL_STAGES
    elif args.stage == "models":
        stages = MODEL_STAGES
    else:
        stages = [args.stage]

    for s in stages:
        t0 = time.time()
        print(f"\n=== {s} ===")
        STAGES[s]()
        print(f"--- {s} done in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
