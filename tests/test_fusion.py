"""
Fusion engine, alert manager and fusion-level evaluation tests.

Most tests use small hand-built data so the expected answer is known exactly.
The last group checks the real pipeline outputs (skipped until `python main.py` runs).
"""
import numpy as np
import pandas as pd
import pytest

import config
from src import alert_manager, evaluation, fusion_engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_snaps(rows, window=0):
    """rows: list of (machine_id, class, raw, calibrated, age_min, target, predicted_alert)."""
    df = pd.DataFrame(rows, columns=["machine_id", "machine_class", "predicted_risk",
                                     "calibrated_risk", "age_min", "target", "predicted_alert"])
    df["window"] = window
    df["window_end"] = pd.Timestamp("2026-01-01") + pd.Timedelta(hours=6 * window)
    return fusion_engine.add_priority_components(df)


def balanced_window(window=0):
    return make_snaps([
        ("M-01", "motor", 0.90, 0.80, 0, 1, 1),
        ("M-02", "motor", 0.80, 0.70, 0, 1, 1),
        ("M-03", "motor", 0.70, 0.60, 0, 0, 1),
        ("P-01", "pump", 0.60, 0.50, 0, 1, 1),
        ("P-02", "pump", 0.20, 0.10, 0, 0, 0),
        ("C-01", "compressor", 0.95, 0.30, 0, 1, 1),   # over-confident raw score
        ("C-02", "compressor", 0.10, 0.05, 0, 0, 0),
    ], window)


# ---------------------------------------------------------------------------
# Freshness and priority
# ---------------------------------------------------------------------------
def test_freshness_factor():
    assert fusion_engine.freshness_factor(0) == 1.0
    assert fusion_engine.freshness_factor(config.FRESHNESS_HALF_LIFE_MIN) == pytest.approx(0.5)
    assert fusion_engine.freshness_factor(2 * config.FRESHNESS_HALF_LIFE_MIN) == pytest.approx(0.25)


def test_priority_formula():
    s = make_snaps([("C-01", "compressor", 0.9, 0.4, config.FRESHNESS_HALF_LIFE_MIN, 1, 1)])
    expected = 0.4 * config.SEVERITY_WEIGHTS["compressor"] * 0.5
    assert s["score_S3_risk_priority"].iloc[0] == pytest.approx(expected)


def test_stale_reading_ranks_lower():
    s = make_snaps([("M-01", "motor", 0.5, 0.5, 0, 0, 0),
                    ("M-02", "motor", 0.5, 0.5, 240, 0, 0)])
    r = fusion_engine.rank_window(s, "S3_risk_priority", k=1)
    assert r.iloc[0]["machine_id"] == "M-01"


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def _val_preds(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for cls in config.MACHINE_CLASSES:
        raw = rng.random(n)
        y = (rng.random(n) < raw ** 2).astype(int)   # raw score is over-confident
        rows.append(pd.DataFrame({"machine_class": cls, "predicted_risk": raw,
                                  "failure_label": y, "split": "val"}))
    return pd.concat(rows, ignore_index=True)


def test_calibrators_refuse_test_data():
    v = _val_preds()
    v.loc[0, "split"] = "test"
    with pytest.raises(ValueError):
        fusion_engine.fit_calibrators(v)


def test_calibration_bounded_monotonic_and_improves_brier():
    v = _val_preds()
    cal = fusion_engine.fit_calibrators(v)
    out = fusion_engine.apply_calibration(_val_preds(seed=1), cal)
    assert out["calibrated_risk"].between(0, 1).all()
    for cls, g in out.groupby("machine_class"):
        g = g.sort_values("predicted_risk")
        assert (g["calibrated_risk"].diff().dropna() >= -1e-12).all(), "calibration must keep within-class order"
    out["split"] = "test"
    rep = fusion_engine.calibration_report(out)
    assert (rep["brier_calibrated"] < rep["brier_raw"]).all()


def test_apply_calibration_unknown_class_fails():
    cal = fusion_engine.fit_calibrators(_val_preds())
    df = pd.DataFrame({"machine_class": ["turbine"], "predicted_risk": [0.5]})
    with pytest.raises(ValueError):
        fusion_engine.apply_calibration(df, cal)


# ---------------------------------------------------------------------------
# Ranking strategies
# ---------------------------------------------------------------------------
def test_s1_ranks_by_raw_score():
    r = fusion_engine.rank_window(balanced_window(), "S1_raw", k=3)
    assert list(r["machine_id"][:3]) == ["C-01", "M-01", "M-02"]


def test_s2_ranks_by_calibrated_risk():
    r = fusion_engine.rank_window(balanced_window(), "S2_calibrated", k=3)
    assert list(r["machine_id"][:3]) == ["M-01", "M-02", "M-03"]
    assert "compressor" not in set(r[r["in_top_k"]]["machine_class"])


def test_rank_is_deterministic_and_complete():
    w = balanced_window()
    for s in config.STRATEGIES:
        r1 = fusion_engine.rank_window(w, s, k=3)
        r2 = fusion_engine.rank_window(w.sample(frac=1, random_state=3), s, k=3)
        assert list(r1["machine_id"]) == list(r2["machine_id"])
        assert sorted(r1["rank"]) == list(range(1, len(w) + 1))
        assert r1["in_top_k"].sum() == 3


def test_s4_guarantees_class_slot_when_eligible():
    r = fusion_engine.rank_window(balanced_window(), "S4_class_fair", k=3)
    top = r[r["in_top_k"]]
    assert "compressor" in set(top["machine_class"])          # C-01 calibrated 0.30 >= 0.20
    assert "pump" in set(top["machine_class"])                # P-01 0.50 x 0.9 = 0.45 > M-03 0.42
    assert top["promoted"].sum() == 1                         # only the compressor needed promoting
    assert top.loc[top["promoted"], "machine_id"].iloc[0] == "C-01"
    # The most represented class (motor) gives up its LOWEST-ranked queue member (M-02).
    assert set(top["machine_id"]) == {"M-01", "P-01", "C-01"}
    assert "promoted: class coverage" in " ".join(top["explanation"])


def test_s4_does_not_force_ineligible_class():
    w = balanced_window()
    w.loc[w["machine_id"] == "C-01", ["calibrated_risk", "score_S3_risk_priority",
                                      "score_S4_class_fair"]] = [0.10, 0.10, 0.10]
    r = fusion_engine.rank_window(w, "S4_class_fair", k=3)
    assert "compressor" not in set(r[r["in_top_k"]]["machine_class"])


def test_s4_equals_s3_when_nothing_to_fix():
    w = make_snaps([("M-01", "motor", .9, .9, 0, 1, 1), ("P-01", "pump", .8, .8, 0, 1, 1),
                    ("C-01", "compressor", .7, .7, 0, 1, 1), ("M-02", "motor", .1, .1, 0, 0, 0)])
    s3 = fusion_engine.rank_window(w, "S3_risk_priority", k=3)
    s4 = fusion_engine.rank_window(w, "S4_class_fair", k=3)
    assert list(s3["machine_id"]) == list(s4["machine_id"])
    assert s4["promoted"].sum() == 0


def test_unknown_strategy_rejected():
    with pytest.raises(ValueError):
        fusion_engine.rank_window(balanced_window(), "S9_magic")


# ---------------------------------------------------------------------------
# Alert manager
# ---------------------------------------------------------------------------
def _stream():
    """Two machines, different rates; M-01 fails at 10:00 on day 2."""
    t0 = pd.Timestamp("2026-03-01 00:00")
    fail = t0 + pd.Timedelta(hours=34)
    rows = []
    for mid, cls, step in [("M-01", "motor", 15), ("C-01", "compressor", 60)]:
        for ts in pd.date_range(t0, t0 + pd.Timedelta(hours=40), freq=f"{step}min"):
            if mid == "M-01" and ts >= fail:
                continue                     # machine down after failure
            ttf = (fail - ts).total_seconds() / 3600 if mid == "M-01" else 500.0
            rows.append({"timestamp": ts, "machine_id": mid, "machine_class": cls,
                         "predicted_risk": 0.5, "predicted_alert": 1, "failure_label": int(ttf <= 24),
                         "time_to_failure_h": ttf})
    return pd.DataFrame(rows), fail


def test_build_windows_one_row_per_machine():
    s, _ = _stream()
    snaps = alert_manager.build_windows(s)
    assert not snaps.duplicated(["window", "machine_id"]).any()
    # The motor reports 4x more often but gets the same single vote per window.
    counts = snaps.groupby("machine_id").size()
    assert counts["C-01"] >= counts["M-01"]


def test_build_windows_target_and_down_machines():
    s, fail = _stream()
    snaps = alert_manager.build_windows(s)
    m = snaps[snaps["machine_id"] == "M-01"]
    for r in m.itertuples():
        hours = (fail - r.window_end).total_seconds() / 3600
        assert r.target == int(0 < hours <= 24)
    # Windows ending after the failure: machine is down, so not in the queue.
    assert (m["window_end"] < fail).all()
    assert (snaps["age_min"] >= 0).all()


def test_new_vs_ongoing():
    r = pd.DataFrame({"window": [0, 1, 2, 4], "machine_id": "M-01", "in_top_k": [True, True, False, True],
                      "rank": 1})
    out = alert_manager.mark_new_vs_ongoing(r)
    assert list(out["alert_status"]) == ["new", "ongoing", "", "new"]


# ---------------------------------------------------------------------------
# Fusion-level evaluation
# ---------------------------------------------------------------------------
def test_buried_and_recall_counts():
    r = fusion_engine.rank_window(balanced_window(), "S2_calibrated", k=3)
    cov = evaluation.topk_class_coverage(r).set_index("machine_class")
    assert cov.loc["compressor", "targets"] == 1
    assert cov.loc["compressor", "captured"] == 0
    assert cov.loc["compressor", "buried"] == 1          # own model alerted, queue left it out
    assert cov.loc["pump", "buried"] == 1
    assert cov.loc["motor", "captured"] == 2


def test_compare_strategies_shapes_and_baseline_delta():
    w = pd.concat([balanced_window(i) for i in range(5)], ignore_index=True)
    ranked = {s: fusion_engine.rank_all_windows(w, s, k=3) for s in config.STRATEGIES}
    comp, per_class = evaluation.compare_strategies(ranked)
    assert set(comp["strategy"]) == set(config.STRATEGIES)
    assert len(per_class) == len(config.STRATEGIES) * len(config.MACHINE_CLASSES)
    assert comp.loc[comp["strategy"] == "S1_raw", "recall_at_k_vs_S1"].isna().all()
    s4 = per_class[(per_class["strategy"] == "S4_class_fair") & (per_class["machine_class"] == "compressor")]
    assert s4["recall_at_k"].iloc[0] == 1.0
    assert ((comp["recall_at_k_ci_low"] <= comp["recall_at_k"] + 1e-9) &
            (comp["recall_at_k"] <= comp["recall_at_k_ci_high"] + 1e-9)).all()


# ---------------------------------------------------------------------------
# Real pipeline outputs (need `python main.py`)
# ---------------------------------------------------------------------------
def _need(path):
    if not path.exists():
        pytest.skip("Run `python main.py` first")


@pytest.mark.parametrize("strategy", list(config.STRATEGIES))
def test_ranked_alert_files(strategy):
    path = config.PREDICTIONS_DIR / f"ranked_alerts_{strategy}.csv"
    _need(path)
    r = pd.read_csv(path)
    assert list(r.columns) == fusion_engine.QUEUE_COLUMNS
    per_window = r.groupby("window")["in_top_k"].sum()
    assert (per_window == config.TOP_K).all()
    assert not r.duplicated(["window", "machine_id"]).any()
    assert r["calibrated_risk"].between(0, 1).all()


def test_strategy_comparison_file():
    path = config.METRICS_DIR / "strategy_comparison.csv"
    _need(path)
    c = pd.read_csv(path)
    assert set(c["strategy"]) == set(config.STRATEGIES)
    assert c["recall_at_k"].between(0, 1).all() and c["precision_at_k"].between(0, 1).all()


def test_calibration_improves_on_real_test_set():
    path = config.METRICS_DIR / "calibration_report.csv"
    _need(path)
    c = pd.read_csv(path)
    assert (c["brier_calibrated"] < c["brier_raw"]).all()
