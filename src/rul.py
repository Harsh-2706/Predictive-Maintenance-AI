"""
Remaining useful life (RUL): how many hours until this machine fails?

The classifiers answer "will it fail in the next 24 h?". For planning (order
parts, book a slot, keep the line running until the weekend) the crew also
needs "how long have we got?".

Model
  One HistGradientBoostingRegressor per machine class, on the same 19 features
  as the classifier, trained on the TRAIN split only.

  Target = min(hours to next failure, RUL_CAP_H). Capping ("piecewise-linear
  RUL", standard practice on NASA C-MAPSS) is used because a healthy machine
  looks the same whether it fails in 4 or 9 days, so long horizons are not
  learnable from sensors; the useful signal is in the last few days.

  Three models per class: the median estimate (absolute-error loss) plus the
  10th and 90th percentiles (quantile loss), giving an 80% range. The range is
  checked on the test set: about 80% of true values should fall inside it.

Evaluation (test split)
  mae_h           mean absolute error over all readings (capped target)
  mae_last24_h    error in the last 24 h before a failure, where decisions happen
  within_6h_last24  share of last-24 h estimates within +-6 h of the truth
  coverage_80     share of readings whose true RUL lies in the 80% range
  naive_mae_h     error of always predicting the training median (a model must beat this)
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import config
from src.data_preprocessing import feature_columns, load_processed

RUL_CAP_H = 72.0
QUANTILES = {"low": 0.1, "high": 0.9}
RUL_PRED_PATH = config.PREDICTIONS_DIR / "rul_predictions.csv"
RUL_METRICS_PATH = config.METRICS_DIR / "rul_metrics.csv"


def rul_path(machine_class: str):
    return config.MODELS_DIR / f"{machine_class}_rul.pkl"


def _regressor(loss: str, quantile: float | None = None) -> HistGradientBoostingRegressor:
    kw = {"quantile": quantile} if quantile is not None else {}
    return HistGradientBoostingRegressor(loss=loss, max_iter=250, learning_rate=0.06, max_depth=6,
                                         random_state=config.RANDOM_SEED, **kw)


def target(df: pd.DataFrame) -> pd.Series:
    return df["time_to_failure_h"].clip(upper=RUL_CAP_H)


def train_class(machine_class: str, df: pd.DataFrame | None = None) -> dict:
    df = load_processed(machine_class) if df is None else df
    features = feature_columns(config.MACHINE_CLASSES[machine_class]["sensors"])
    train = df[df["split"] == "train"]
    X, y = train[features], target(train)
    models = {"median": _regressor("absolute_error").fit(X, y)}
    for name, q in QUANTILES.items():
        models[name] = _regressor("quantile", q).fit(X, y)
    bundle = {"models": models, "features": features, "machine_class": machine_class,
              "cap_h": RUL_CAP_H, "naive_h": float(y.median()), "train_rows": len(train),
              "trained_at": pd.Timestamp.now().isoformat(timespec="seconds")}
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, rul_path(machine_class))
    return bundle


def load_rul(machine_class: str) -> dict:
    return joblib.load(rul_path(machine_class))


def predict_frame(bundle: dict, X: pd.DataFrame) -> pd.DataFrame:
    """Median estimate and 80% range, clipped to [0, cap] and kept ordered."""
    f = X[bundle["features"]]
    med = np.clip(bundle["models"]["median"].predict(f), 0, bundle["cap_h"])
    lo = np.clip(bundle["models"]["low"].predict(f), 0, bundle["cap_h"])
    hi = np.clip(bundle["models"]["high"].predict(f), 0, bundle["cap_h"])
    lo, hi = np.minimum(lo, med), np.maximum(hi, med)
    return pd.DataFrame({"rul_h": med, "rul_low_h": lo, "rul_high_h": hi}, index=X.index)


def evaluate(pred: pd.DataFrame, naive_h: float) -> dict:
    y = pred["rul_true_h"]
    err = (pred["rul_h"] - y).abs()
    last = y <= config.FAILURE_HORIZON_HOURS
    inside = (y >= pred["rul_low_h"]) & (y <= pred["rul_high_h"])
    return {
        "readings": int(len(pred)),
        "mae_h": float(err.mean()),
        "naive_mae_h": float((naive_h - y).abs().mean()),
        "mae_last24_h": float(err[last].mean()),
        "naive_mae_last24_h": float((naive_h - y[last]).abs().mean()),
        "within_6h_last24": float((err[last] <= 6).mean()),
        "bias_last24_h": float((pred["rul_h"] - y)[last].mean()),
        "coverage_80": float(inside.mean()),
        "coverage_80_last24": float(inside[last].mean()),
        "mean_range_width_h": float((pred["rul_high_h"] - pred["rul_low_h"]).mean()),
    }


def run_rul(save: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    preds, rows = [], []
    for cls in config.MACHINE_CLASSES:
        df = load_processed(cls)
        bundle = train_class(cls, df)
        part = df[df["split"].isin(["val", "test"])]
        p = predict_frame(bundle, part)
        p = pd.concat([part[["timestamp", "machine_id", "machine_class", "split"]], p], axis=1)
        p["rul_true_h"] = target(part)
        preds.append(p)
        rows.append({"machine_class": cls, **evaluate(p[p["split"] == "test"], bundle["naive_h"])})
    pred = pd.concat(preds, ignore_index=True)
    metrics = pd.DataFrame(rows)
    if save:
        config.PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        config.METRICS_DIR.mkdir(parents=True, exist_ok=True)
        out = pred[pred["split"] == "test"].drop(columns="split")
        out[["rul_h", "rul_low_h", "rul_high_h", "rul_true_h"]] = out[
            ["rul_h", "rul_low_h", "rul_high_h", "rul_true_h"]].round(2)
        out.to_csv(RUL_PRED_PATH, index=False)
        metrics.round(4).to_csv(RUL_METRICS_PATH, index=False)
    return pred, metrics


def load_rul_predictions() -> pd.DataFrame:
    return pd.read_csv(RUL_PRED_PATH, parse_dates=["timestamp"])
