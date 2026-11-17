"""
Tests for the upgrades: baselines + savings, remaining useful life, model health
(drift), technician feedback and CSV scoring.

Unit tests use small synthetic data. Integration tests are skipped until
`python main.py` has produced models and results.
"""
import numpy as np
import pandas as pd
import pytest

import config
from src import baselines, batch_scoring, feedback, model_health

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _have_outputs():
    return (config.METRICS_DIR / "baseline_comparison.csv").exists() and \
        all((config.MODELS_DIR / f"{c}_rul.pkl").exists() for c in config.MACHINE_CLASSES)


needs_pipeline = pytest.mark.skipif(not _have_outputs(), reason="Run `python main.py` first")


# ---------------------------------------------------------------------------
# Drift (PSI)
# ---------------------------------------------------------------------------
def test_psi_zero_for_same_distribution_and_large_for_shift():
    rng = np.random.default_rng(0)
    ref = rng.normal(50, 5, 20000)
    edges = model_health.bin_edges(ref)
    base = model_health.shares(ref, edges)
    same = model_health.psi(base, model_health.shares(rng.normal(50, 5, 5000), edges))
    shifted = model_health.psi(base, model_health.shares(rng.normal(55, 5, 5000), edges))
    assert same < model_health.PSI_WATCH
    assert shifted > model_health.PSI_DRIFT
    assert model_health.psi_status(same) == "stable" and model_health.psi_status(shifted) == "drift"


# ---------------------------------------------------------------------------
# Baseline selection rules
# ---------------------------------------------------------------------------
def _snaps(n_machines=10, n_windows=6, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for w in range(n_windows):
        for i in range(n_machines):
            rows.append({"window": w, "window_end": pd.Timestamp("2026-04-07") + pd.Timedelta(hours=6 * (w + 1)),
                         "machine_id": f"M-{i:02d}", "machine_class": "motor",
                         "temperature": rng.normal(60, 2), "vibration": rng.normal(2, 0.2), "rpm": rng.normal(1500, 10),
                         "target": int(rng.random() < 0.2)})
    return pd.DataFrame(rows)


def test_schedule_visits_k_per_shift_and_cycles_whole_fleet():
    s = baselines.select_schedule(_snaps(), k=3)
    assert (s.groupby("window")["visited"].sum() == 3).all()
    # 10 machines, 3 per shift -> every machine visited within ceil(10/3)=4 shifts
    first4 = s[s["window"] < 4]
    assert set(first4.loc[first4["visited"], "machine_id"]) == set(s["machine_id"])


def test_threshold_only_visits_alarms_largest_first():
    s = _snaps()
    s.loc[(s["window"] == 2) & (s["machine_id"] == "M-03"), "temperature"] = 60 + 8 * 2   # 8 sigma
    s.loc[(s["window"] == 2) & (s["machine_id"] == "M-07"), "vibration"] = 2 + 4 * 0.2    # 4 sigma
    stats = {"motor": {"temperature": {"mean": 60, "std": 2}, "vibration": {"mean": 2, "std": 0.2},
                       "rpm": {"mean": 1500, "std": 10}}}
    out = baselines.select_threshold(s, k=1, stats=stats)
    w2 = out[out["window"] == 2]
    assert w2.loc[w2["visited"], "machine_id"].tolist() == ["M-03"]          # k=1: largest deviation wins
    assert out["visited"].sum() <= out["alarm"].sum()                      # never visits a non-alarm


def test_savings_arithmetic_and_reactive_reference():
    comp = pd.DataFrame([
        {"approach": "reactive", "events_caught": 0, "events_missed": 10, "inspections": 0, "days": 30},
        {"approach": "ai", "events_caught": 8, "events_missed": 2, "inspections": 100, "days": 30},
    ])
    costs = {"downtime_cost_per_hour": 1000, "breakdown_downtime_hours": 10, "planned_downtime_hours": 2,
             "breakdown_repair_cost": 5000, "planned_repair_cost": 1000, "inspection_cost": 10}
    out = baselines.savings(comp, costs, period_days=30)["rows"].set_index("approach")
    assert out.loc["reactive", "total"] == 10 * (10 * 1000 + 5000)
    assert out.loc["ai", "total"] == 2 * 15000 + 8 * (2 * 1000 + 1000) + 100 * 10
    assert out.loc["reactive", "saving_vs_reactive"] == 0
    with pytest.raises(ValueError):
        baselines.savings(comp, {**costs, "inspection_cost": -1})


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
def test_feedback_roundtrip(tmp_path):
    path = tmp_path / "fb.csv"
    base = {"machine_id": "P-06", "machine_class": "pump", "window": 40, "window_end": "2026-04-17T00:00:00",
            "risk": 0.93, "queue_rank": 1}
    feedback.record({**base, "outcome": "fault_found", "note": "  impeller\nwear " + "x" * 400}, path)
    feedback.record({**base, "machine_id": "M-04", "machine_class": "motor", "outcome": "no_fault"}, path)
    feedback.record({**base, "machine_id": "C-07", "machine_class": "compressor", "outcome": "not_checked"}, path)
    s = feedback.summary(path)
    assert s["total"] == 3 and s["counts"]["fault_found"] == 1
    assert s["confirmed_precision"] == 0.5                     # not_checked is excluded
    assert len(feedback.load(path)["note"].iloc[0]) <= feedback.MAX_NOTE
    labels = feedback.training_labels(path)
    assert sorted(labels["label"].tolist()) == [0, 1]
    with pytest.raises(ValueError):
        feedback.record({**base, "outcome": "maybe"}, path)


# ---------------------------------------------------------------------------
# CSV validation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,msg", [
    ("a,b\n1,2", "Missing column"),
    ("timestamp,machine_id,machine_class,temperature\n2026-01-01,X-1,boiler,1", "Unknown machine_class"),
    ("timestamp,machine_id,machine_class,temperature\n2026-01-01,M-1,motor,1", "need sensor"),
    ("timestamp,machine_id,machine_class,temperature,vibration,rpm\nnot-a-date,M-1,motor,1,2,3", "No timestamp"),
])
def test_csv_validation_errors(text, msg):
    with pytest.raises(ValueError, match=msg):
        batch_scoring.validate(batch_scoring.read_csv(text))


# ---------------------------------------------------------------------------
# Integration (after `python main.py`)
# ---------------------------------------------------------------------------
@needs_pipeline
def test_ai_beats_alarm_limits_and_schedule():
    comp = baselines.load_comparison().set_index("approach")
    assert comp.loc["ai", "recall_at_k"] > comp.loc["threshold", "recall_at_k"] > comp.loc["schedule", "recall_at_k"]
    assert comp.loc["threshold", "ai_recall_gain_ci_low"] > 0          # gain is statistically real
    assert comp.loc["reactive", "events_caught"] == 0
    assert (comp["events_caught"] <= comp["failure_events"]).all()


@needs_pipeline
def test_rul_beats_naive_and_ranges_are_ordered():
    m = pd.read_csv(config.METRICS_DIR / "rul_metrics.csv")
    assert (m["mae_last24_h"] < m["naive_mae_last24_h"]).all()
    p = pd.read_csv(config.PREDICTIONS_DIR / "rul_predictions.csv")
    assert (p["rul_low_h"] <= p["rul_h"] + 1e-6).all() and (p["rul_h"] <= p["rul_high_h"] + 1e-6).all()
    assert p[["rul_low_h", "rul_h", "rul_high_h"]].min().min() >= 0


@pytest.fixture(scope="module")
def client():
    if not _have_outputs():
        pytest.skip("Run `python main.py` first")
    from api.main import app
    return TestClient(app)


@needs_pipeline
def test_uploaded_csv_reproduces_live_queue(client):
    """Scoring the sample file must give the same queue as the live system for that shift."""
    from api.main import svc
    w = int(len(svc().windows) * 0.42)
    csv = client.get(f"/api/sample-csv?window={w}").text
    up = client.post("/api/score-csv?k=8", files={"file": ("s.csv", csv, "text/csv")})
    assert up.status_code == 200
    live = client.get(f"/api/window/{w}?strategy=S3_risk_priority&k=8").json()
    assert [m["machine_id"] for m in up.json()["queue"]] == [m["id"] for m in live["queue"]]


@needs_pipeline
def test_score_csv_rejects_bad_file(client):
    r = client.post("/api/score-csv", files={"file": ("bad.csv", "x,y\n1,2", "text/csv")})
    assert r.status_code == 422 and "Missing column" in r.json()["detail"]


@needs_pipeline
def test_savings_endpoint_and_validation(client):
    body = {**baselines.DEFAULT_COSTS, "period_days": 30}
    r = client.post("/api/savings", json=body).json()
    rows = {x["approach"]: x for x in r["rows"]}
    assert rows["ai"]["total"] < rows["reactive"]["total"]
    assert client.post("/api/savings", json={**body, "inspection_cost": -5}).status_code == 422


@needs_pipeline
def test_health_detects_injected_sensor_fault(client):
    clean = client.get("/api/health/model").json()
    assert all(r["status"] == "stable" for r in clean["worst"])
    hit = client.get("/api/health/model?inject_class=pump&inject_sensor=flow_rate&inject_pct=-8").json()
    flow = [r for r in hit["worst"] if r["machine_class"] == "pump" and r["sensor"] == "flow_rate"][0]
    assert flow["status"] == "drift"
    assert client.get("/api/health/model?inject_class=pump&inject_sensor=rpm&inject_pct=5").status_code == 422


@needs_pipeline
def test_feedback_endpoint(client, tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, "FEEDBACK_PATH", tmp_path / "fb.csv")
    top = client.get("/api/window/40?strategy=S3_risk_priority&k=8").json()["queue"][0]["id"]
    r = client.post(f"/api/machine/{top}/feedback", json={"window": 40, "outcome": "fault_found", "note": "test"})
    assert r.status_code == 200 and r.json()["summary"]["total"] == 1
    assert r.json()["saved"]["queue_rank"] == 1
    assert client.post(f"/api/machine/{top}/feedback", json={"window": 40, "outcome": "?"}).status_code == 422
    assert client.get("/api/feedback").json()["counts"]["fault_found"] == 1


@needs_pipeline
def test_window_items_carry_remaining_life(client):
    q = client.get("/api/window/40?strategy=S3_risk_priority&k=8").json()["queue"]
    assert all(m["rul_h"] is not None and m["rul_low_h"] <= m["rul_h"] <= m["rul_high_h"] for m in q)
