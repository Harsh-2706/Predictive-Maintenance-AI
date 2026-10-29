# AI-Powered Predictive Maintenance Platform (Multi-Machine Ensemble)

**Technical report.** All numbers in this report are produced by `python main.py`
(seed 42) and can be regenerated. Source files are given for every table.

---

## 1. Abstract

Predictive-maintenance models are usually built one machine type at a time.
When a plant runs several such models, their outputs cannot be ranked against
each other directly: the models are trained on different sensors, at different
data rates, and their scores are calibrated differently. We build a platform
that fuses three machine-specific models (motor, pump, compressor; 60 machines)
into one prioritised maintenance queue, and test whether the fusion rule
systematically hides real failures from any machine class.

Two findings matter. First, raw model scores are not comparable. The
compressor model reports an average risk of 21% where the true rate is 8%.
Per-class isotonic calibration reduces probability error (Brier score) by
24–53%. Second, calibration alone is not safe for the queue. With crew
capacity of 8 machines per 6-hour shift, it lowers the share of real
compressor failures that reach the queue by 6.7 points (95% CI −11.8 to −2.1).
Weighting calibrated risk by failure consequence and data freshness removes
this loss with no significant change in overall recall (0.828 vs 0.830).

## 2. Problem and research question

**Problem.** Isolated single-machine pilots give no fleet-wide answer to
*"which machines should the crew inspect first?"*

**Research question.** How should predictions from models trained on different
machine classes, with different data rates and confidence calibrations, be
combined into one prioritised alert stream, without systematically burying real
alerts from any one class?

**Target.** `failure_label = 1` if the machine fails within the next **24 hours**.

**Fairness meaning.** This is operational fairness across machine classes, not
demographic fairness. Each class should get comparable recall, and no class's
real failures should be consistently pushed out of the queue.

## 3. System architecture

```
Sensor streams (60 machines, 3 rates)
   → time-based features (2 h / 6 h windows)
   → one model per class (RF / GB / LR)            src/train_models.py
   → common prediction contract                     src/predict.py
   → alert manager: 1 snapshot per machine / 6 h    src/alert_manager.py
   → per-class calibration (fit on validation)      src/fusion_engine.py
   → priority = risk × severity × freshness
   → optional class-coverage safeguard
   → top-k maintenance queue → dashboard            dashboard/app.py
   → fusion-level fairness evaluation               src/evaluation.py
```

## 4. Data

**Simulated multi-machine plant** (`src/data_simulator.py`). Public PdM datasets
each cover a single machine type, so they cannot test cross-class fusion.
Simulation controls exactly the variables in the research question.

| Class | Machines | Sampling | Mean run-to-failure | Signal noise | Dropouts |
|---|---|---|---|---|---|
| Motor | 30 | 15 min | 8 days | 1.0× | 1% |
| Pump | 18 | 30 min | 10 days | 1.3× | 3% |
| Compressor | 12 | 60 min | 12 days | 1.8× | 6% |

The simulation covers 120 days and 763 failure events. Each machine runs in
cycles. Degradation follows `d = (t/T)³`, so symptoms appear late. Sensor
values are made up of a baseline, an operating-load effect, a degradation
effect, noise, and a per-machine offset. Each failure is followed by 4 h of
maintenance downtime, and random dropouts and outages create stale data.

**Split.** Chronological 60/20/20 split with a 24 h purge gap before each
cutoff. The gap is needed because the label looks 24 h ahead.

## 5. Per-class models (model-level evaluation)

Each class has its own model, trained with `class_weight="balanced"`. Test set,
threshold 0.5 (`results/metrics/model_metrics.csv`):

| Class | Model | Precision | Recall | Miss rate | PR-AUC | Mean predicted risk | Actual rate |
|---|---|---|---|---|---|---|---|
| Motor | Random Forest | 0.673 | 0.907 | 0.093 | 0.885 | 0.170 | 0.122 |
| Pump | Gradient Boosting | 0.596 | 0.957 | 0.043 | 0.900 | 0.182 | 0.110 |
| Compressor | Logistic Regression | 0.398 | 0.934 | 0.066 | 0.674 | 0.213 | 0.080 |

Recall is similar across classes, so no class is missed at the model stage.
Calibration is not similar. All three models over-predict risk, and the
compressor model is worst (`results/figures/reliability_raw_val.png`).

## 6. Fusion and prioritisation logic

**Review windows.** Every 6 h, the queue is built from **one snapshot per
machine**, taken from its latest reading. Counting every reading, motors would
generate 70% of alerts only because they report four times as often as
compressors. Windowing reduces their share to 47%
(`results/metrics/alert_volume_by_class.csv`).

**Four strategies.** Each strategy adds exactly one idea to the previous one,
so the comparison works as an ablation:

| ID | Priority score | Idea tested |
|---|---|---|
| S1 | raw model score | baseline |
| S2 | calibrated risk p̂ | make scores comparable |
| S3 | p̂ × severity × freshness | add consequence and data age |
| S4 | S3 + class-coverage safeguard | guarantee visibility per class |

- **Calibration.** We fit per-class isotonic regression on validation
  predictions only. It is monotonic, so the order of machines within a class
  is preserved. Only the meaning of the numbers changes.
- **Severity.** The weights are compressor 1.0, pump 0.9, motor 0.7. These
  are *assumed* consequence weights; in deployment they would be replaced by
  downtime cost per hour.
- **Freshness.** `0.5^(age_min / 120)`, so a 2-hour-old reading counts half.
- **Safeguard (S4).** A class with no machine in the top-k, but with one at
  calibrated risk ≥ 0.20, gets that machine in. It replaces the lowest-ranked
  machine of the most-represented class.
- **No double-counting.** We do not multiply by a separate "confidence" term,
  because calibration already expresses how trustworthy a score is.

## 7. Experiments and results

The test set covers 95 review windows, 60 machines, and a top-8 queue per
window. 95% CIs come from a paired bootstrap over windows, with 1,000
resamples (`results/metrics/strategy_comparison.csv`).

| Strategy | Recall@8 (95% CI) | Precision@8 | Severity-weighted recall | Worst-class recall | Buried alerts |
|---|---|---|---|---|---|
| S1 raw | 0.830 (0.804–0.858) | 0.674 | 0.833 | 0.812 | 68 |
| S2 calibrated | 0.830 (0.802–0.858) | 0.674 | 0.828 | 0.789 | 68 |
| S3 risk priority | 0.828 (0.803–0.857) | 0.672 | 0.831 | 0.809 | 69 |
| S4 class-fair | 0.823 (0.796–0.852) | 0.668 | 0.827 | 0.804 | 72 |

**Calibration quality on test** (`calibration_report.csv`): the Brier score
improves for every class. Compressor 0.088 → 0.041 (−53%), pump 0.053 → 0.029
(−45%), motor 0.046 → 0.035 (−24%).

**Per class, compressor** (`strategy_per_class.csv`):

| Strategy | Recall@8 | Change vs S1 (95% CI) | Queue share | Share of real failures |
|---|---|---|---|---|
| S1 | 0.856 | — | 21% | 15% |
| S2 | 0.789 | −0.067 (−0.118 to −0.021) | 19% | 15% |
| S3 | 0.856 | 0.000 (−0.033 to +0.032) | 21% | 15% |
| S4 | 0.856 | 0.000 (−0.033 to +0.032) | 22% | 15% |

**Capacity sensitivity** (`k_sensitivity.csv`, `k_sensitivity.png`): at k = 4,
compressor recall is 0.51 under S1, **0.24 under S2**, 0.51 under S3, and
**0.63 under S4**. The tighter the crew capacity, the more the choice of
strategy matters.

## 8. Fairness analysis

1. **Model level.** Recall differs across classes by only 0.05. Unfairness, if
   any, would be introduced by the fusion step.
2. **Raw ranking (S1)** gives compressors more queue slots than their failure
   share, because the compressor model's over-confidence buys slots with false
   alarms. This looks fair, but only by accident: a differently trained
   (under-confident) compressor model would reverse it. S1 is not a reliable
   policy.
3. **Calibration alone (S2) buries compressor failures.** This is the
   statistically significant loss above. The mechanism is that the compressor
   model is the least separable (PR-AUC 0.67), so after calibration even its
   true failures receive only moderate probabilities, and sharper motor
   predictions outrank them. A probability-optimal ranking is not automatically
   consequence-optimal or class-fair.
4. **Consequence weighting (S3) removes the loss** at default capacity, with no
   significant change in overall recall.
5. **The safeguard (S4)** costs about 0.5 points of overall recall at k = 8 but
   protects compressors (the weakest model) most when capacity is tight. It cut
   the number of windows in which compressors had no slot at all from 16 to 10.
6. **Severity is a policy trade-off.** At k = 4, S3 moves slots from motors
   (lowest severity) to pumps and compressors: motor recall falls 0.51 → 0.41
   while pump recall rises 0.55 → 0.73. Overall recall is nearly unchanged
   (0.525 → 0.517). This is intended only if motor failures really cost less,
   so in deployment the weights must come from plant downtime costs.

**Recommendation.** Use S3 as the default ranking. Enable S4 when crew
capacity is tight relative to alert volume.

## 9. Web app and dashboard

The main frontend is a web app: a FastAPI backend (`api/`) that loads the trained
models, and a React + ECharts frontend (`frontend/`). The models run **live** in two
places:
- The *Why* panel re-scores a machine with one sensor at a time set to its healthy
  level, showing what drives the risk.
- The *What-if* simulator re-scores a machine after sensor changes and re-ranks the
  shift.

An API test confirms that the live scores equal the pipeline's saved predictions.

The app has six pages: story, control room (live floor-map replay with the ranked
queue), machine detail, fairness lab, models, and method. The original Streamlit
dashboard (`dashboard/app.py`) is kept as a second frontend over the same outputs.

## 10. Limitations and future work

- **Simulated data.** The results show how the fusion logic behaves under
  controlled conditions. They do not demonstrate accuracy on real equipment.
- Severity weights are assumed values, not plant cost data.
- Event-level recall saturates near 1.0, because the simulated degradation is
  strong close to failure.
- A single threshold (0.5) is used for model-level alerts.
- **Next steps:** a pilot on historian/SCADA data from one line; severity from
  downtime-cost data; online recalibration with drift monitoring; and a learned
  (rather than fixed) fusion weight, evaluated on the same fairness metrics.

## 11. References

- Niculescu-Mizil, A., & Caruana, R. (2005). Predicting good probabilities with supervised learning. *ICML*.
- Zadrozny, B., & Elkan, C. (2002). Transforming classifier scores into accurate multiclass probability estimates. *KDD*.
- Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review*.
- Saxena, A., et al. (2008). Damage propagation modeling for aircraft engine run-to-failure simulation (C-MAPSS). *PHM*.
- Matzka, S. (2020). Explainable AI for predictive maintenance applications (AI4I 2020 dataset). *AI4I*.
- Efron, B., & Tibshirani, R. (1993). *An Introduction to the Bootstrap*. Chapman & Hall.
