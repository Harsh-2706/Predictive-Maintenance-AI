
"""
Build a compact deployment artifact for model-health monitoring.

Reads the existing processed datasets without modifying them.
Preserves the original PSI reference-bin calculations and test readings.
"""

import joblib
import numpy as np
import pandas as pd

import config
from src.model_health import bin_edges, shares, PSI_BINS


def build_health_artifact():
    artifact = {
        "version": 1,
        "psi_bins": PSI_BINS,
        "psi_watch": 0.10,
        "psi_drift": 0.25,
        "classes": {},
    }

    for cls, spec in config.MACHINE_CLASSES.items():
        print(f"Processing {cls}...")

        df = pd.read_csv(
            config.DATA_PROC_DIR / f"{cls}_processed.csv",
            parse_dates=["timestamp"],
        )

        sensors = spec["sensors"]
        train = df[df["split"] == "train"]
        test = df[df["split"] == "test"]

        reference = {}

        for sensor in sensors:
            values = train[sensor].to_numpy()
            edges = bin_edges(values, PSI_BINS)
            proportions = shares(values, edges)

            reference[sensor] = {
                "edges": edges,
                "shares": proportions,
            }

        test_data = test[["timestamp"] + sensors].copy()

        artifact["classes"][cls] = {
            "sensors": sensors,
            "reference": reference,
            "test": test_data,
        }

        print(
            f"  Training rows: {len(train):,}"
            f" | Test rows: {len(test):,}"
        )

    output = config.MODELS_DIR / "health_artifact.pkl"
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(artifact, output, compress=3)

    size_mb = output.stat().st_size / (1024 * 1024)

    print(f"\nArtifact created: {output}")
    print(f"Artifact size: {size_mb:.2f} MB")


if __name__ == "__main__":
    build_health_artifact()
