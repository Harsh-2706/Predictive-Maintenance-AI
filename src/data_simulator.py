"""
Simulated multi-machine sensor data pipeline.

WHY SIMULATED DATA?
Public predictive-maintenance datasets each cover a single machine type
(e.g. NASA C-MAPSS = turbofan engines, AI4I 2020 = one milling machine).
Combining them would mean different units, labels and failure definitions.
A simulator lets us control exactly the things our R&D question is about:
different data rates, different failure prevalence, different signal quality.
LIMITATION: results show how the fusion logic behaves, not real-world
industrial accuracy. This must be stated in the report.

HOW IT WORKS (per machine):
1. Split the timeline into run-to-failure cycles. Cycle lengths are random
   (gamma distribution around the class mean).
2. Inside a cycle, a degradation level d goes from 0 (healthy) to 1 (failure)
   along d = (t / cycle_length) ** 3, i.e. degradation shows up late.
3. Sensors = baseline + load effect + degradation effect + noise.
4. After each failure the machine is down for MAINTENANCE_HOURS, then resets.
5. Some readings are dropped (random dropouts + short outages) to create
   stale data, more often for classes with higher dropout_prob.
6. Label: failure_label = 1 if the next failure is within FAILURE_HORIZON_HOURS.
"""
import numpy as np
import pandas as pd

import config

MAINTENANCE_HOURS = 4


def _cycle_boundaries(rng, total_hours, mean_cycle_days):
    """Return list of (cycle_start_h, failure_h) covering the timeline and beyond."""
    cycles = []
    t = -rng.uniform(0, mean_cycle_days * 24)  # machine is mid-life at sim start
    shape = 6.0                                # gamma shape -> moderate variance
    while t < total_hours:
        length = rng.gamma(shape, mean_cycle_days * 24 / shape)
        length = max(length, 48.0)             # at least 2 days per cycle
        cycles.append((t, t + length))
        t = t + length + MAINTENANCE_HOURS
    return cycles


def _sensor_values(machine_class, d, load, noise, offset):
    """Physical-ish sensor model for each class. d = degradation 0..1."""
    if machine_class == "motor":
        return {
            "temperature": 60 + 3 * load + 15 * d + offset[0] + 2.0 * noise[0],
            "vibration": 2 + 0.5 * load + 4 * d ** 1.5 + offset[1] + 0.4 * noise[1],
            "rpm": 1500 + 20 * load - 80 * d + offset[2] * 10 + 15 * noise[2],
        }
    if machine_class == "pump":
        return {
            "pressure": 5 + 0.5 * load - 1.5 * d + offset[0] * 0.2 + 0.3 * noise[0],
            "flow_rate": 100 + 4 * load - 25 * d + offset[1] * 2 + 4.0 * noise[1],
            "temperature": 45 + 2 * load + 8 * d + offset[2] + 1.5 * noise[2],
        }
    if machine_class == "compressor":
        return {
            "temperature": 80 + 3 * load + 12 * d + offset[0] + 3.0 * noise[0],
            "pressure": 8 + 0.6 * load + 2 * d + offset[1] * 0.2 + 0.5 * noise[1],
            "vibration": 1.5 + 0.3 * load + 2 * d + offset[2] * 0.2 + 0.5 * noise[2],
        }
    raise ValueError(f"Unknown machine class: {machine_class}")


def simulate_machine(rng, machine_class, machine_id, params, start, total_hours):
    step_h = params["sample_every_min"] / 60
    t = np.arange(0, total_hours, step_h)
    cycles = _cycle_boundaries(rng, total_hours, params["mean_cycle_days"])

    degradation = np.full(t.shape, np.nan)
    time_to_failure = np.full(t.shape, np.nan)
    for c_start, c_fail in cycles:
        mask = (t >= c_start) & (t < c_fail)
        frac = (t[mask] - c_start) / (c_fail - c_start)
        degradation[mask] = frac ** 3
        time_to_failure[mask] = c_fail - t[mask]

    running = ~np.isnan(degradation)           # False during maintenance downtime
    t, degradation, time_to_failure = t[running], degradation[running], time_to_failure[running]
    # Rounded before labelling so the label and the saved value always agree and
    # files are byte-identical across numpy versions.
    time_to_failure = np.round(time_to_failure, 6)

    # Operating load: daily cycle + slow random drift (not related to failure).
    load = np.sin(2 * np.pi * t / 24) + 0.3 * rng.standard_normal(t.shape)
    noise = rng.standard_normal((3, t.size)) * params["noise_scale"]
    offset = rng.normal(0, 1, 3)               # machine-to-machine variation
    sensors = _sensor_values(machine_class, degradation, load, noise, offset)

    df = pd.DataFrame({
        "timestamp": pd.Timestamp(start) + pd.to_timedelta(t, unit="h"),
        "machine_id": machine_id,
        "machine_class": machine_class,
        **sensors,
        "time_to_failure_h": time_to_failure,
        "failure_label": (time_to_failure <= config.FAILURE_HORIZON_HOURS).astype(int),
    })

    # Data quality issues -> stale readings.
    keep = rng.random(len(df)) > params["dropout_prob"]
    n_outages = rng.poisson(config.SIM_DAYS / 15)          # ~1 outage per 15 days
    for _ in range(n_outages):
        o_start = rng.uniform(0, total_hours)
        o_len = rng.uniform(1, 4)
        keep &= ~((t >= o_start) & (t < o_start + o_len))
    df = df[keep].reset_index(drop=True)

    failures = [
        {"machine_id": machine_id, "machine_class": machine_class,
         "failure_time": (pd.Timestamp(start) + pd.to_timedelta(f, unit="h")).round("s")}
        for _, f in cycles if 0 <= f < total_hours
    ]
    return df, failures


def simulate_all(save=True):
    rng = np.random.default_rng(config.RANDOM_SEED)
    total_hours = config.SIM_DAYS * 24
    all_failures = []
    frames = {}
    prefix = {"motor": "M", "pump": "P", "compressor": "C"}

    for machine_class, params in config.MACHINE_CLASSES.items():
        parts = []
        for i in range(1, params["n_machines"] + 1):
            machine_id = f"{prefix[machine_class]}-{i:02d}"
            df, failures = simulate_machine(rng, machine_class, machine_id, params,
                                            config.SIM_START, total_hours)
            parts.append(df)
            all_failures.extend(failures)
        frames[machine_class] = pd.concat(parts, ignore_index=True)

    failures_df = pd.DataFrame(all_failures).sort_values("failure_time")

    if save:
        config.DATA_SIM_DIR.mkdir(parents=True, exist_ok=True)
        for machine_class, df in frames.items():
            df.to_csv(config.DATA_SIM_DIR / f"{machine_class}_raw.csv", index=False)
        failures_df.to_csv(config.DATA_SIM_DIR / "failure_events.csv", index=False)

    return frames, failures_df


def summarise(frames, failures_df):
    rows = []
    for machine_class, df in frames.items():
        rows.append({
            "machine_class": machine_class,
            "machines": df["machine_id"].nunique(),
            "readings": len(df),
            "sample_every_min": config.MACHINE_CLASSES[machine_class]["sample_every_min"],
            "failure_events": int((failures_df["machine_class"] == machine_class).sum()),
            "positive_rate": round(df["failure_label"].mean(), 4),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    frames, failures = simulate_all()
    print(summarise(frames, failures).to_string(index=False))
