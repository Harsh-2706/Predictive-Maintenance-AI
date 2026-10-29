# Research Logbook — Multi-Machine Predictive Maintenance Platform

**Owner:** _(name)_ · **Team:** _(names)_

Rules:
1. Record only work actually done and numbers the code actually produced.
2. Date every entry with the real date.
3. Each entry answers: *what problem → what we chose and why (over what
   alternative) → what we expected → what happened → what we changed next.*

Evidence for every entry already exists in the repo. Cite the file.

| # | Entry | Evidence to cite |
|---|---|---|
| 1 | Problem definition and target (fails within 24 h) | `README.md` §Problem, `config.py` |
| 2 | Data: why simulated, class design, data rates | `src/data_simulator.py`, `config.MACHINE_CLASSES`, simulate-stage output |
| 3 | Baseline models and model-level fairness | `results/metrics/model_metrics.csv`, `confusion_matrices_test.png`, `reliability_raw_val.png` |
| 4 | Data-rate problem at alert level → review windows | `results/metrics/alert_volume_by_class.csv` |
| 5 | Calibration design and result | `results/metrics/calibration_report.csv`, `calibration_before_after.png` |
| 6 | Four-strategy experiment (S1–S4) | `results/metrics/strategy_comparison.csv`, `strategy_per_class.csv` |
| 7 | Fairness finding: calibration alone buries compressor failures | `strategy_per_class.csv` (`recall_vs_S1` CI), `recall_at_k_by_class.png` |
| 8 | Capacity sensitivity | `results/metrics/k_sensitivity.csv`, `k_sensitivity.png` |
| 9 | Failure analysis (what did not work, what changed) | own notes, git history |
| 10 | Final results, limitations, next steps | `report/project_report.md` §7–10 |

---

## Entry 1 — _title_ · _date_

**Problem / question:**

**Decision and alternatives considered:**

**Expected:**

**Result (with file reference):**

**What we changed next:**

---

_(copy the block above for each entry)_
