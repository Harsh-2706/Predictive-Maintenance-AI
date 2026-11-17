
import numpy as np
import pandas as pd

import config
from src.model_health import HealthMonitor, bin_edges, shares, PSI_BINS


def main():
    # New implementation: compact artifact
    optimized = HealthMonitor()

    # Original implementation: processed CSVs
    original = HealthMonitor.__new__(HealthMonitor)
    original.ref = {}
    original.cur = {}

    for cls, spec in config.MACHINE_CLASSES.items():
        df = pd.read_csv(
            config.DATA_PROC_DIR / f"{cls}_processed.csv",
            parse_dates=["timestamp"],
        )

        train = df[df["split"] == "train"]

        original.ref[cls] = {}
        for sensor in spec["sensors"]:
            values = train[sensor].to_numpy()
            edges = bin_edges(values, PSI_BINS)
            original.ref[cls][sensor] = (
                edges,
                shares(values, edges),
            )

        original.cur[cls] = df.loc[
            df["split"] == "test",
            ["timestamp"] + spec["sensors"]
        ].reset_index(drop=True)

    start = min(c["timestamp"].min() for c in original.cur.values())
    original.start = start.normalize()

    # Compare reference distributions
    for cls in config.MACHINE_CLASSES:
        for sensor in config.MACHINE_CLASSES[cls]["sensors"]:
            old_edges, old_shares = original.ref[cls][sensor]
            new_edges, new_shares = optimized.ref[cls][sensor]

            np.testing.assert_array_equal(old_edges, new_edges)
            np.testing.assert_allclose(
                old_shares, new_shares, rtol=0, atol=0
            )

    # Compare complete drift outputs
    old = original.drift()
    new = optimized.drift()

    pd.testing.assert_frame_equal(
        old["weekly"].reset_index(drop=True),
        new["weekly"].reset_index(drop=True),
        check_exact=True,
    )

    pd.testing.assert_frame_equal(
        old["worst"].reset_index(drop=True),
        new["worst"].reset_index(drop=True),
        check_exact=True,
    )

    print("\nSUCCESS: Original and optimized PSI results match exactly.")
    print("Reference distributions: IDENTICAL")
    print("Weekly PSI results: IDENTICAL")
    print("Worst drift results: IDENTICAL")


if __name__ == "__main__":
    main()
