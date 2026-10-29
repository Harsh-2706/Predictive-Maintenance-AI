"""
Maintenance control-room dashboard.

    streamlit run dashboard/app.py

Reads only files produced by `python main.py` (results/, data/simulated/),
so every number on screen comes from the same pipeline as the report.

Tabs
  1. Alert queue      what the maintenance lead sees each 6 h review window
  2. Machine detail   sensor history, raw vs calibrated risk, failures
  3. Fairness         strategy comparison, per-class recall, buried alerts
  4. Models           per-class model metrics and calibration
  5. Method           architecture, formulas, assumptions, limitations
"""
from pathlib import Path
import json
import re
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

CLASS_COLORS = {"motor": "#2a6fdb", "pump": "#e07b00", "compressor": "#2e9e57"}
STRATEGY_COLORS = {"S1_raw": "#9aa0a6", "S2_calibrated": "#5b8def",
                   "S3_risk_priority": "#1f3f8f", "S4_class_fair": "#d9534f"}
DEFAULT_STRATEGY = "S3_risk_priority"

st.set_page_config(page_title="Predictive Maintenance Control Room", page_icon="⚙️", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 1.6rem;}
  div[data-testid="stMetricValue"] {font-size: 1.7rem;}
  .finding {border-left: 4px solid #1f3f8f; padding: .5rem .9rem; margin: .4rem 0;
            background: rgba(31,63,143,.06); border-radius: 4px;}
  .warnbox {border-left: 4px solid #d9534f; padding: .5rem .9rem; margin: .4rem 0;
            background: rgba(217,83,79,.06); border-radius: 4px;}
</style>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _missing(path):
    st.error(f"Missing `{path.relative_to(config.ROOT)}`. Run `python main.py` from the project root first.")
    st.stop()


@st.cache_data
def load_csv(rel_path, parse_dates=None):
    path = config.ROOT / rel_path
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=parse_dates)


def need(rel_path, parse_dates=None):
    df = load_csv(rel_path, parse_dates)
    if df is None:
        _missing(config.ROOT / rel_path)
    return df


@st.cache_data
def load_sensors(machine_class, machine_id):
    path = config.DATA_SIM_DIR / f"{machine_class}_raw.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["timestamp"])
    return df[df["machine_id"] == machine_id]


queues = {s: need(f"results/predictions/ranked_alerts_{s}.csv", ["window_end"])
          for s in config.STRATEGIES}
comparison = need("results/metrics/strategy_comparison.csv")
per_class = need("results/metrics/strategy_per_class.csv")
sensitivity = need("results/metrics/k_sensitivity.csv")
model_metrics = need("results/metrics/model_metrics.csv")
calibration = need("results/metrics/calibration_report.csv")
volume = need("results/metrics/alert_volume_by_class.csv")
test_preds = need("results/predictions/predictions_test.csv", ["timestamp"])
failures = load_csv("data/simulated/failure_events.csv", ["failure_time"])
run_meta = json.loads((config.METRICS_DIR / "fusion_run.json").read_text())

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("⚙️ Control room")
strategy = st.sidebar.selectbox(
    "Prioritisation strategy", list(config.STRATEGIES),
    index=list(config.STRATEGIES).index(DEFAULT_STRATEGY), key="strategy",
    format_func=lambda s: f"{s} — {config.STRATEGIES[s]}")
q = queues[strategy]
windows = q[["window", "window_end"]].drop_duplicates().sort_values("window")
labels = windows["window_end"].dt.strftime("%d %b %H:%M").tolist()
label = st.sidebar.select_slider("Review window (end time)", options=labels,
                                 value=labels[len(labels) // 2], key="window")
w_end = windows["window_end"].iloc[labels.index(label)]
show_truth = st.sidebar.toggle("Evaluation mode: reveal ground truth", value=False, key="truth",
                               help="Shows which machines actually failed within 24 h. "
                                    "Not available to a real control room.")
st.sidebar.divider()
st.sidebar.caption(
    f"Fleet: {run_meta['machines']} machines · {len(config.MACHINE_CLASSES)} classes\n\n"
    f"Queue capacity: top-{run_meta['top_k']} every {run_meta['review_window_hours']} h\n\n"
    f"Test period: {run_meta['windows']} review windows\n\n"
    "Data: simulated (see Method tab)")

st.title("Multi-Machine Predictive Maintenance Platform")
st.caption("One prioritised maintenance queue from three machine-specific models — "
           "calibrated, consequence-aware, and checked for class fairness.")

tab_queue, tab_machine, tab_fair, tab_models, tab_method = st.tabs(
    ["🚨 Alert queue", "🔧 Machine detail", "⚖️ Fairness & strategies", "📈 Models", "📐 Method"])

# ---------------------------------------------------------------------------
# 1. Alert queue
# ---------------------------------------------------------------------------
with tab_queue:
    win = q[q["window_end"] == w_end].sort_values("rank")
    top = win[win["in_top_k"]]
    high_risk = (win["calibrated_risk"] >= 0.5).sum()

    c = st.columns(5)
    c[0].metric("Machines reporting", len(win))
    c[1].metric("In maintenance queue", len(top))
    c[2].metric("New alerts", int((top["alert_status"] == "new").sum()))
    c[3].metric("High risk (calibrated ≥ 0.5)", int(high_risk))
    c[4].metric("Stale readings (> 60 min)", int((win["age_min"] > 60).sum()))

    left, right = st.columns([3, 2])
    with left:
        st.subheader(f"Maintenance queue — {w_end:%d %b %Y, %H:%M}")
        cols = ["rank", "machine_id", "machine_class", "alert_status", "priority_score",
                "calibrated_risk", "predicted_risk", "severity", "freshness", "explanation"]
        if show_truth:
            cols.append("target")
        view = top[cols].rename(columns={
            "machine_id": "machine", "machine_class": "class", "alert_status": "status",
            "priority_score": "priority", "calibrated_risk": "calibrated risk",
            "predicted_risk": "raw score", "target": "fails <24h"})
        st.dataframe(view, hide_index=True, width="stretch",
                     column_config={
                         "priority": st.column_config.ProgressColumn(format="%.2f", min_value=0, max_value=1),
                         "calibrated risk": st.column_config.NumberColumn(format="%.2f"),
                         "raw score": st.column_config.NumberColumn(format="%.2f"),
                         "freshness": st.column_config.NumberColumn(format="%.2f"),
                     })
        if show_truth:
            missed = win[(win["target"] == 1) & ~win["in_top_k"]]
            caught = int(top["target"].sum())
            st.markdown(f"**Ground truth:** {caught} of {int(win['target'].sum())} machines that fail "
                        f"within 24 h are in the queue; {len(top) - caught} queue slots are false alarms.")
            if len(missed):
                st.markdown("<div class='warnbox'><b>Missed by the queue:</b> " +
                            ", ".join(f"{r.machine_id} (rank {r.rank})" for r in missed.itertuples()) +
                            "</div>", unsafe_allow_html=True)

    with right:
        st.subheader("Fleet risk map")
        fleet = win.copy()
        fleet["status"] = fleet["in_top_k"].map({True: "in queue", False: ""})
        fig = px.scatter(fleet, x="machine_class", y="calibrated_risk", color="machine_class",
                         symbol="status", symbol_map={"in queue": "star", "": "circle"},
                         color_discrete_map=CLASS_COLORS, hover_name="machine_id",
                         hover_data={"priority_score": ":.2f", "predicted_risk": ":.2f",
                                     "machine_class": False, "status": False},
                         labels={"calibrated_risk": "Calibrated risk", "machine_class": ""})
        fig.update_traces(marker=dict(size=11, line=dict(width=1, color="white")))
        fig.update_layout(height=420, showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")
        st.caption("★ = machine in the maintenance queue. Each dot is one machine's latest reading.")

# ---------------------------------------------------------------------------
# 2. Machine detail
# ---------------------------------------------------------------------------
with tab_machine:
    machines = sorted(test_preds["machine_id"].unique())
    default = top["machine_id"].iloc[0] if len(top) else machines[0]
    mid = st.selectbox("Machine", machines, index=machines.index(default), key="machine")
    mcls = test_preds.loc[test_preds["machine_id"] == mid, "machine_class"].iloc[0]
    sensors = config.MACHINE_CLASSES[mcls]["sensors"]
    st.markdown(f"**{mid}** · {mcls} · model: `{config.MODEL_CHOICE[mcls]}` · "
                f"samples every {config.MACHINE_CLASSES[mcls]['sample_every_min']} min · "
                f"severity weight {config.SEVERITY_WEIGHTS[mcls]}")

    mq = q[q["machine_id"] == mid].sort_values("window_end")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=mq["window_end"], y=mq["predicted_risk"], name="raw score",
                             line=dict(color="#9aa0a6", dash="dot")))
    fig.add_trace(go.Scatter(x=mq["window_end"], y=mq["calibrated_risk"], name="calibrated risk",
                             line=dict(color=CLASS_COLORS[mcls], width=3)))
    inq = mq[mq["in_top_k"]]
    fig.add_trace(go.Scatter(x=inq["window_end"], y=inq["calibrated_risk"], mode="markers",
                             name="in queue", marker=dict(symbol="star", size=11, color="#d9534f")))
    if failures is not None:
        for t in failures[(failures["machine_id"] == mid) &
                          (failures["failure_time"].between(mq["window_end"].min(),
                                                            mq["window_end"].max()))]["failure_time"]:
            fig.add_vline(x=t, line=dict(color="black", width=1.5, dash="dash"))
    fig.add_vline(x=w_end, line=dict(color="#1f3f8f", width=1))
    fig.update_layout(height=320, yaxis_title="Risk", yaxis_range=[0, 1.02],
                      margin=dict(t=20, b=10), legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, width="stretch")
    st.caption("Black dashed lines = actual failures. Blue line = selected review window.")

    sd = load_sensors(mcls, mid)
    if sd is None:
        st.info("Sensor history needs `data/simulated/` — run `python main.py`.")
    else:
        sd = sd[sd["timestamp"] >= test_preds["timestamp"].min()]
        fig = px.line(sd.melt(id_vars="timestamp", value_vars=sensors), x="timestamp", y="value",
                      facet_row="variable", height=120 + 150 * len(sensors))
        fig.update_yaxes(matches=None, title=None)
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
        fig.update_traces(line=dict(color=CLASS_COLORS[mcls], width=1))
        fig.update_layout(margin=dict(t=20, b=10))
        st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------------------
# 3. Fairness & strategies
# ---------------------------------------------------------------------------
with tab_fair:
    st.subheader("Key findings (computed from this run)")
    pc = per_class.set_index(["strategy", "machine_class"])
    cal = calibration.set_index("machine_class")
    worst_cal = cal["mean_raw_risk"].sub(cal["actual_rate"]).idxmax()
    s2c = pc.loc[("S2_calibrated", "compressor")]
    s3c = pc.loc[("S3_risk_priority", "compressor")]
    s1c = pc.loc[("S1_raw", "compressor")]
    sig = s2c["recall_vs_S1_ci_high"] < 0
    findings = [
        f"Raw model scores are not comparable: the **{worst_cal}** model predicts "
        f"{cal.loc[worst_cal, 'mean_raw_risk']:.0%} average risk where the real rate is "
        f"{cal.loc[worst_cal, 'actual_rate']:.0%}. Per-class calibration cuts Brier error by "
        f"{calibration['brier_improvement_pct'].min():.0f}–{calibration['brier_improvement_pct'].max():.0f}%.",
        f"Under raw scores, compressors take **{s1c['queue_share']:.0%}** of queue slots while causing "
        f"{s1c['failure_share']:.0%} of failures — over-confidence buys them slots with false alarms.",
        f"Calibration alone (S2) **buries compressor failures**: recall {s1c['recall_at_k']:.2f} → "
        f"{s2c['recall_at_k']:.2f} (change {s2c['recall_vs_S1']:+.3f}, 95% CI "
        f"{s2c['recall_vs_S1_ci_low']:+.3f} to {s2c['recall_vs_S1_ci_high']:+.3f}"
        f"{', significant' if sig else ''}).",
        f"Adding consequence and freshness (S3) restores compressor recall to {s3c['recall_at_k']:.2f} "
        f"with no significant change in overall recall.",
    ]
    tight = sensitivity[sensitivity["k"] == 4].set_index("strategy")
    if {"S1_raw", "S3_risk_priority"} <= set(tight.index):
        findings.append(
            f"Severity is a policy trade-off: with a crew of 4, S3 moves slots from motors to pumps "
            f"and compressors (motor recall {tight.loc['S1_raw', 'recall_motor']:.2f} → "
            f"{tight.loc['S3_risk_priority', 'recall_motor']:.2f}, pump "
            f"{tight.loc['S1_raw', 'recall_pump']:.2f} → {tight.loc['S3_risk_priority', 'recall_pump']:.2f}). "
            f"Weights should come from real downtime costs.")
    for f in findings:
        # Markdown is not parsed inside raw HTML, so convert **bold** to <b>bold</b>.
        f = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", f)
        st.markdown(f"<div class='finding'>{f}</div>", unsafe_allow_html=True)

    st.subheader(f"Strategy comparison — top-{config.TOP_K}, test set")
    comp = comparison.copy()
    comp["recall@k (95% CI)"] = comp.apply(
        lambda r: f"{r.recall_at_k:.3f} ({r.recall_at_k_ci_low:.3f}–{r.recall_at_k_ci_high:.3f})", axis=1)
    comp["worst-class recall (95% CI)"] = comp.apply(
        lambda r: f"{r.min_class_recall:.3f} ({r.min_class_recall_ci_low:.3f}–{r.min_class_recall_ci_high:.3f})", axis=1)
    st.dataframe(comp[["strategy", "description", "recall@k (95% CI)", "precision_at_k",
                       "severity_weighted_recall", "worst-class recall (95% CI)",
                       "recall_disparity", "buried_total", "promoted_total"]].round(3),
                 hide_index=True, width="stretch")

    a, b = st.columns(2)
    with a:
        pcv = per_class.copy()
        pcv["err_plus"] = pcv["recall_ci_high"] - pcv["recall_at_k"]
        pcv["err_minus"] = pcv["recall_at_k"] - pcv["recall_ci_low"]
        fig = px.bar(pcv, x="machine_class", y="recall_at_k", color="strategy", barmode="group",
                     error_y="err_plus", error_y_minus="err_minus",
                     color_discrete_map=STRATEGY_COLORS,
                     labels={"recall_at_k": f"Recall@{config.TOP_K}", "machine_class": ""},
                     title="Real failures reaching the queue, by class (95% CI)")
        fig.update_layout(yaxis_range=[0, 1.05], height=400, legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, width="stretch")
    with b:
        k_metric = st.radio("Capacity curve", ["min_class_recall", "recall_at_k", "recall_compressor"],
                            horizontal=True, key="k_metric",
                            format_func={"min_class_recall": "worst class", "recall_at_k": "overall",
                                         "recall_compressor": "compressor"}.get)
        fig = px.line(sensitivity, x="k", y=k_metric, color="strategy", markers=True,
                      color_discrete_map=STRATEGY_COLORS,
                      labels={"k": "Queue capacity per 6 h window", k_metric: "Recall"},
                      title="How results change with crew capacity")
        fig.add_vline(x=config.TOP_K, line_dash="dot")
        fig.update_layout(yaxis_range=[0, 1.02], height=400, legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")

    st.subheader("Who gets the maintenance slots?")
    share = per_class[["strategy", "machine_class", "queue_share"]].rename(columns={"queue_share": "share"})
    actual = per_class[per_class["strategy"] == "S1_raw"][["machine_class", "failure_share"]] \
        .rename(columns={"failure_share": "share"}).assign(strategy="Actual failures")
    share = pd.concat([actual, share])
    fig = px.bar(share, x="strategy", y="share", color="machine_class", text_auto=".0%",
                 color_discrete_map=CLASS_COLORS, labels={"share": "", "strategy": ""})
    fig.update_layout(height=360, yaxis_tickformat=".0%")
    st.plotly_chart(fig, width="stretch")

    st.subheader("Per-class detail")
    st.dataframe(per_class[["strategy", "machine_class", "targets", "captured", "missed", "buried",
                            "false_alarms_in_queue", "recall_at_k", "recall_vs_S1",
                            "recall_vs_S1_ci_low", "recall_vs_S1_ci_high", "queue_share",
                            "failure_share", "windows_with_zero_slots"]].round(3),
                 hide_index=True, width="stretch")
    st.caption("buried = the machine's own model raised an alert, it truly failed within 24 h, "
               "but the fused queue left it out. A CI on recall_vs_S1 that excludes 0 is a real effect.")

# ---------------------------------------------------------------------------
# 4. Models
# ---------------------------------------------------------------------------
with tab_models:
    split = st.radio("Split", ["test", "val"], horizontal=True, key="split")
    cols = ["machine_class", "model_name", "readings", "prevalence", "precision", "recall", "fnr",
            "f1", "pr_auc", "brier", "calibration_gap", "event_recall", "median_lead_time_h"]
    st.dataframe(model_metrics[model_metrics["split"] == split][cols].round(3),
                 hide_index=True, width="stretch")
    st.caption("Reading-level metrics at threshold 0.5. Accuracy is deliberately not shown: "
               "with ~10% positives, a model that never alerts would score ~90%.")
    c1, c2 = st.columns(2)
    c1.image(str(config.FIGURES_DIR / f"confusion_matrices_{split}.png"))
    c2.image(str(config.FIGURES_DIR / f"pr_curves_{split}.png"))
    st.subheader("Calibration before and after")
    st.image(str(config.FIGURES_DIR / "calibration_before_after.png"))
    st.dataframe(calibration.round(3), hide_index=True, width="stretch")
    st.subheader("Data-rate effect")
    st.dataframe(volume.round(3), hide_index=True, width="stretch")
    st.caption("Counting every reading, motors produce most alerts simply because they report "
               "4× more often than compressors. One snapshot per machine per window removes that bias.")

# ---------------------------------------------------------------------------
# 5. Method
# ---------------------------------------------------------------------------
with tab_method:
    st.subheader("Architecture")
    st.graphviz_chart("""
    digraph {
      rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eef2fb", fontname="Helvetica"];
      sim [label="Sensor data\\nmotor 15 min · pump 30 min\\ncompressor 60 min"];
      feat [label="Time-based features\\n2 h / 6 h windows"];
      m1 [label="Motor model\\nRandom Forest", fillcolor="#dbe7fb"];
      m2 [label="Pump model\\nGradient Boosting", fillcolor="#fbe9d6"];
      m3 [label="Compressor model\\nLogistic Regression", fillcolor="#dcf1e3"];
      win [label="Alert manager\\n1 snapshot / machine / 6 h"];
      cal [label="Per-class calibration\\n(isotonic, fit on validation)"];
      pri [label="Priority = risk × severity × freshness"];
      fair [label="Class-coverage safeguard\\n(optional, S4)"];
      q [label="Top-k maintenance queue", fillcolor="#f9dedc"];
      ev [label="Fairness evaluation\\nper-class recall@k, buried alerts, bootstrap CIs"];
      sim -> feat -> {m1 m2 m3} -> win -> cal -> pri -> fair -> q -> ev;
    }""")
    st.subheader("Priority formula")
    st.latex(r"\text{priority}_i = \hat p_i \times S_{c(i)} \times 0.5^{\,\text{age}_i / %d}"
             % config.FRESHNESS_HALF_LIFE_MIN)
    st.markdown(f"""
- **p̂ᵢ** — calibrated probability that machine *i* fails within {config.FAILURE_HORIZON_HOURS} h
  (per-class isotonic regression fitted on validation data only).
- **S** — severity weight per class: {', '.join(f'{k} {v}' for k, v in config.SEVERITY_WEIGHTS.items())}.
  *Assumed* values; in deployment replace with downtime cost per hour.
- **age** — minutes since the machine's last reading; half-life {config.FRESHNESS_HALF_LIFE_MIN} min.
- **Safeguard (S4)** — each class keeps ≥ {config.MIN_SLOTS_PER_CLASS} slot if it has a machine with
  calibrated risk ≥ {config.MIN_ELIGIBLE_RISK}.
""")
    st.subheader("Evaluation protocol")
    st.markdown(f"""
- Chronological split 60/20/20 with a {config.FAILURE_HORIZON_HOURS} h purge gap (no label leakage).
- Models trained on train; calibration fitted on validation; **all strategy results on the untouched test set**.
- Ground truth per window: machine fails within {config.FAILURE_HORIZON_HOURS} h after the window ends.
- 95% confidence intervals: paired bootstrap over review windows ({config.BOOTSTRAP_ITERS} resamples).
""")
    st.subheader("Limitations")
    st.markdown("""
- **Simulated data.** Shows how the fusion logic behaves under controlled conditions; does not prove
  accuracy on real equipment. Next step: pilot on historian data from one plant line.
- **Severity weights are assumptions**, not derived from plant cost data.
- Event-level recall saturates near 1.0 because simulated degradation is strong close to failure.
- At tight capacity, raw scores show better worst-class recall — but only because the compressor
  model's over-confidence happens to favour compressors. That would reverse with a different model,
  so it is not a property we can rely on.
""")
