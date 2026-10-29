"""
Model-pipeline tests: data simulator, preprocessing, and the prediction contract.

Run from the project root:   python -m pytest -q
Tests that need pipeline outputs are skipped until `python main.py` has run.
"""
import numpy as np
import pandas as pd
import pytest

import config
from src import data_preprocessing, data_simulator
from src.predict import CONTRACT_COLUMNS


def _small_machine(machine_class="motor", days=20):
    rng = np.random.default_rng(0)
    params = config.MACHINE_CLASSES[machine_class]
    df, failures = data_simulator.simulate_machine(rng, machine_class, "X-01", params,
                                                   config.SIM_START, days * 24)
    return df, failures


@pytest.mark.parametrize("machine_class", list(config.MACHINE_CLASSES))
def test_simulator_schema(machine_class):
    df, _ = _small_machine(machine_class)
    for col in ["timestamp", "machine_id", "machine_class", "failure_label", "time_to_failure_h"]:
        assert col in df.columns
    for s in config.MACHINE_CLASSES[machine_class]["sensors"]:
        assert s in df.columns and df[s].notna().all()
    assert set(df["failure_label"].unique()) <= {0, 1}


def test_label_matches_horizon():
    df, _ = _small_machine()
    expected = (df["time_to_failure_h"] <= config.FAILURE_HORIZON_HOURS).astype(int)
    assert (df["failure_label"] == expected).all()


def test_sampling_rate_respected():
    df, _ = _small_machine("compressor")
    gaps = df["timestamp"].diff().dt.total_seconds().div(60).dropna()
    # Minimum gap equals the configured sampling interval (dropouts only make gaps longer).
    assert gaps.min() == pytest.approx(config.MACHINE_CLASSES["compressor"]["sample_every_min"])


def test_degradation_signal_present():
    """Readings close to failure should have higher motor temperature on average."""
    df, _ = _small_machine("motor", days=60)
    assert df.loc[df["failure_label"] == 1, "temperature"].mean() > \
           df.loc[df["failure_label"] == 0, "temperature"].mean()


def test_chronological_split_and_purge():
    df, _ = _small_machine(days=config.SIM_DAYS)
    out = data_preprocessing.assign_split(df)
    train_end, val_end = data_preprocessing.split_cutoffs()
    assert out.loc[out["split"] == "train", "timestamp"].max() < train_end
    assert out.loc[out["split"] == "val", "timestamp"].min() >= train_end
    assert out.loc[out["split"] == "test", "timestamp"].min() >= val_end
    # No training row may have its label window reaching into validation.
    gap = pd.Timedelta(hours=config.FAILURE_HORIZON_HOURS)
    assert out.loc[out["split"] == "train", "timestamp"].max() < train_end - gap


def test_features_are_time_based():
    df, _ = _small_machine()
    sensors = config.MACHINE_CLASSES["motor"]["sensors"]
    feats = data_preprocessing.add_features(df, sensors)
    for c in data_preprocessing.feature_columns(sensors):
        assert c in feats.columns
        assert feats[c].notna().all()


# ---------------------------------------------------------------------------
# Contract tests: need `python main.py` to have produced predictions.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("split", ["val", "test"])
def test_prediction_contract(split):
    path = config.PREDICTIONS_DIR / f"predictions_{split}.csv"
    if not path.exists():
        pytest.skip("Run `python main.py` first")
    p = pd.read_csv(path)
    assert list(p.columns) == CONTRACT_COLUMNS
    assert p["predicted_risk"].between(0, 1).all()
    assert set(p["machine_class"]) == set(config.MACHINE_CLASSES)
    assert (p["split"] == split).all()
    assert ((p["predicted_risk"] >= config.ALERT_THRESHOLD).astype(int) == p["predicted_alert"]).all()
