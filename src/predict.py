"""
Generate predictions in the COMMON PREDICTION CONTRACT.

This file is the interface between the models and the fusion engine. Whatever model a
class uses, its output is written with exactly these columns:

    timestamp            when the reading was taken
    machine_id           e.g. M-03, P-01, C-05
    machine_class        motor | pump | compressor
    predicted_risk       model's raw probability of failure within the horizon
    predicted_alert      1 if predicted_risk >= config.ALERT_THRESHOLD
    failure_label        ground truth (1 = fails within FAILURE_HORIZON_HOURS)
    time_to_failure_h    ground truth hours until next failure (evaluation only)
    minutes_since_last   gap to previous reading (data freshness input)
    model_name           algorithm used
    model_version        config.MODEL_VERSION
    split                val | test

Files written:
    results/predictions/predictions_val.csv   -> fusion engine fits calibration here
    results/predictions/predictions_test.csv  -> final evaluation only

predicted_risk is deliberately RAW (uncalibrated). Calibration belongs to the
fusion engine so that raw vs calibrated ranking can be compared.
"""
import pandas as pd

import config
from src.data_preprocessing import load_processed
from src.train_models import load_model

CONTRACT_COLUMNS = [
    "timestamp", "machine_id", "machine_class", "predicted_risk", "predicted_alert",
    "failure_label", "time_to_failure_h", "minutes_since_last",
    "model_name", "model_version", "split",
]


def predict_class(machine_class, splits=("val", "test"), df=None):
    bundle = load_model(machine_class)
    df = load_processed(machine_class) if df is None else df
    df = df[df["split"].isin(splits)].copy()
    # Rounded to 6 decimals: Random Forest's parallel trees can differ in the
    # ~16th decimal between runs; rounding makes saved files byte-identical.
    df["predicted_risk"] = bundle["model"].predict_proba(df[bundle["features"]])[:, 1].round(6)
    df["predicted_alert"] = (df["predicted_risk"] >= config.ALERT_THRESHOLD).astype(int)
    df["model_name"] = bundle["model_name"]
    df["model_version"] = bundle["model_version"]
    return df[CONTRACT_COLUMNS]


def predict_all(processed=None, save=True):
    processed = processed or {}
    preds = pd.concat(
        [predict_class(c, df=processed.get(c)) for c in config.MACHINE_CLASSES],
        ignore_index=True,
    ).sort_values(["timestamp", "machine_id"]).reset_index(drop=True)

    if save:
        config.PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        for split in ("val", "test"):
            preds[preds["split"] == split].to_csv(
                config.PREDICTIONS_DIR / f"predictions_{split}.csv", index=False)
    return preds


def load_predictions(split):
    return pd.read_csv(config.PREDICTIONS_DIR / f"predictions_{split}.csv",
                       parse_dates=["timestamp"])


if __name__ == "__main__":
    p = predict_all()
    print(p.groupby(["split", "machine_class"]).size())
