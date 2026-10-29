"""
Dashboard smoke test: renders every tab and drives every control headlessly.
Skipped if Streamlit is not installed or `python main.py` has not been run.
"""
import pytest

import config

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(config.ROOT / "dashboard" / "app.py")


@pytest.fixture(scope="module")
def app():
    if not (config.METRICS_DIR / "strategy_comparison.csv").exists():
        pytest.skip("Run `python main.py` first")
    at = AppTest.from_file(APP, default_timeout=180).run()
    assert not at.exception, at.exception
    return at


def test_renders_all_tabs(app):
    assert [t.label.split(" ", 1)[1] for t in app.tabs] == \
        ["Alert queue", "Machine detail", "Fairness & strategies", "Models", "Method"]
    assert not app.error


def test_queue_size_matches_config(app):
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["In maintenance queue"] == str(config.TOP_K)


def test_every_control(app):
    for s in config.STRATEGIES:
        app.selectbox(key="strategy").set_value(s).run()
        assert not app.exception, (s, app.exception)
    app.toggle(key="truth").set_value(True).run()
    assert not app.exception
    app.selectbox(key="machine").set_value("C-03").run()
    opts = app.select_slider(key="window").options
    for o in [opts[0], opts[-1], opts[len(opts) // 3]]:
        app.select_slider(key="window").set_value(o).run()
        assert not app.exception, (o, app.exception)
    assert app.selectbox(key="machine").value == "C-03", "machine choice must survive a window change"
    for m in ["P-07", "M-21", "C-12"]:
        app.selectbox(key="machine").set_value(m).run()
        assert not app.exception, (m, app.exception)
    radios = {"split": ["test", "val"],
              "k_metric": ["min_class_recall", "recall_at_k", "recall_compressor"]}
    for key, values in radios.items():
        for v in values:
            app.radio(key=key).set_value(v).run()
            assert not app.exception, (key, v, app.exception)
