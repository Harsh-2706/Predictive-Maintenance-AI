"""
Web API tests (FastAPI). Skipped until `python main.py` has produced models and results.
The key check: the live model inside the API reproduces the pipeline's saved predictions.
"""
import pytest

import config

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client():
    if not (config.METRICS_DIR / "k_sensitivity.csv").exists() or \
            not (config.MODELS_DIR / "motor_model.pkl").exists():
        pytest.skip("Run `python main.py` first")
    from api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def service(client):
    from api.main import svc
    return svc()


def test_health_and_fleet(client):
    assert client.get("/api/health").json()["machines"] == 60
    f = client.get("/api/fleet").json()
    assert len(f["machines"]) == 60
    assert {c["id"] for c in f["classes"]} == set(config.MACHINE_CLASSES)
    assert len(f["windows"]) > 50


@pytest.mark.parametrize("strategy", list(config.STRATEGIES))
@pytest.mark.parametrize("k", [3, 8])
def test_window_queue_size_and_order(client, strategy, k):
    w = client.get(f"/api/window/40?strategy={strategy}&k={k}").json()
    assert len(w["machines"]) == 60                      # every machine, incl. not reporting
    assert [m["rank"] for m in w["queue"]] == list(range(1, k + 1))
    assert all(m["in_queue"] for m in w["queue"])


def test_window_matches_saved_ranking(client):
    import pandas as pd
    saved = pd.read_csv(config.PREDICTIONS_DIR / "ranked_alerts_S3_risk_priority.csv")
    expected = saved[(saved["window"] == 40) & saved["in_top_k"]].sort_values("rank")["machine_id"].tolist()
    got = [m["id"] for m in client.get(f"/api/window/40?strategy=S3_risk_priority&k={config.TOP_K}").json()["queue"]]
    assert got == expected


def test_live_model_reproduces_pipeline_predictions(client, service):
    """Explain re-runs the real model on features rebuilt from raw data; must equal the saved score."""
    snaps = service.snaps[service.snaps["window"] == 40].nlargest(5, "predicted_risk")
    for row in snaps.itertuples():
        ex = client.get(f"/api/machine/{row.machine_id}/explain/40").json()
        assert ex["raw"] == pytest.approx(row.predicted_risk, abs=1e-4)
        assert ex["risk"] == pytest.approx(row.calibrated_risk, abs=1e-4)
        assert {d["sensor"] for d in ex["drivers"]} == set(config.MACHINE_CLASSES[row.machine_class]["sensors"])


def test_what_if_zero_change_is_identity(client, service):
    row = service.snaps[service.snaps["window"] == 40].nlargest(1, "predicted_risk").iloc[0]
    r = client.post(f"/api/machine/{row.machine_id}/what-if", json={"window": 40, "deltas": {}}).json()
    assert r["raw"] == pytest.approx(row.predicted_risk, abs=1e-4)
    assert r["rank"] == r["rank_before"]


def test_what_if_moves_risk_and_rank(client, service):
    row = service.snaps[(service.snaps["window"] == 40) &
                        (service.snaps["machine_class"] == "compressor")].nlargest(1, "predicted_risk").iloc[0]
    healthy_drop = client.post(f"/api/machine/{row.machine_id}/what-if",
                               json={"window": 40, "deltas": {"vibration": -3, "temperature": -15}}).json()
    assert healthy_drop["risk"] < row.calibrated_risk
    assert healthy_drop["rank"] >= healthy_drop["rank_before"]


def test_machine_detail(client):
    m = client.get("/api/machine/C-08").json()
    assert m["cls"] == "compressor" and len(m["timeline"]) > 50
    assert [s["name"] for s in m["sensors"]] == config.MACHINE_CLASSES["compressor"]["sensors"]
    assert all(0 <= t["risk"] <= 1 for t in m["timeline"])


def test_analysis_endpoints_are_json_safe(client):
    for path in ["/api/story", "/api/calibration", "/api/fairness", "/api/models"]:
        r = client.get(path)
        assert r.status_code == 200, path
    story = client.get("/api/story").json()
    assert story["compressor"]["S2_calibrated"]["delta"] < 0
    assert 0 < story["failures_in_test"] < 763


@pytest.mark.parametrize("path,code", [
    ("/api/machine/X-99", 404),
    ("/api/window/9999", 404),
    ("/api/window/1?strategy=S9", 422),
    ("/api/window/1?k=0", 422),
    ("/api/nope", 404),
])
def test_errors(client, path, code):
    assert client.get(path).status_code == code


def test_what_if_rejects_unknown_sensor(client):
    r = client.post("/api/machine/C-08/what-if", json={"window": 40, "deltas": {"rpm": 5}})
    assert r.status_code == 422
