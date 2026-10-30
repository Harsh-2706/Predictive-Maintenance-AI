# FairQueue PdM: AI-Powered Predictive Maintenance Platform (Multi-Machine Ensemble)

A platform that combines failure predictions from **three different machine types**
(motors, pumps, compressors — 60 machines) into **one prioritised maintenance queue**.
It checks with statistics that the queue does not quietly hide real failures from any
one machine type.

> **Problem.** Plants run separate predictive-maintenance pilots per machine type.
> Each model speaks its own "language": a score of 0.8 from the compressor model
> does not mean the same as 0.8 from the motor model. So there is no reliable way
> to answer *"which machines should the crew inspect first?"*

**Stack:** Python 3.10+ · pandas · scikit-learn (Random Forest, Gradient Boosting,
Logistic Regression, isotonic calibration) · **FastAPI** backend serving the live models ·
**React + Apache ECharts** web app · original Streamlit dashboard kept as a second
frontend · pytest · GitHub Actions CI.

**Two frontends, same results:**

| Frontend | Start it with | Open | Use it for |
|---|---|---|---|
| **Web app (React + FastAPI)**: main demo | `run_web.bat` | http://localhost:8000 | Client and industry presentations: story, live control room, what-if simulator |
| Streamlit dashboard: original | `run_streamlit.bat` | http://localhost:8501 | Quick analysis view; kept as the first version |

Both read the same pipeline outputs, so every number matches.

---

## Application at a glance

FairQueue turns class-specific failure estimates into a transparent, six-hour maintenance decision: models estimate failure risk, calibration makes probabilities comparable, and the selected policy allocates limited crew capacity. The app keeps the evidence, queue, and simulation limits visible together.

## Web application screenshots

The gallery is intentionally awaiting genuine captures from the current running application. No verified UI screenshots were present in the repository, and no mockups or stock imagery have been substituted. Capture instructions and the exact filenames are in [docs/screenshots/README.md](docs/screenshots/README.md).

| View | Planned asset | What it demonstrates |
|---|---|---|
| Control Room | `docs/screenshots/control-room.png` | The live, capacity-constrained maintenance queue. |
| Fairness Lab | `docs/screenshots/fairness-lab.png` | Strategy and crew-capacity trade-offs by machine class. |
| Models & Calibration | `docs/screenshots/models-calibration.png` | Model evidence and calibrated failure probabilities. |
| Machine Detail | `docs/screenshots/machine-detail.png` | Sensor history, explanation, and live what-if re-ranking. |
| Method | `docs/screenshots/method.png` | The six-stage predictive-maintenance pipeline. |

---

## 👉 Teammate: start here

The platform is built, tested and running. **Your part is the research logbook,
extended testing, enhancements, and rehearsing the demo.** Follow these steps in order.

### Step 1: Get it running on your laptop (about 30 minutes, once)

1. Install **Python 3.10–3.12** from python.org. On the first installer screen, tick
   **"Add python.exe to PATH"**.
2. Install **Git** from git-scm.com (default options are fine).
3. Clone the repo into a normal folder, **not inside OneDrive** (OneDrive syncing makes
   setup very slow):
   ```powershell
   cd C:\Users\<you>\Documents
   git clone https://github.com/Harsh-2706/Predictive-Maintenance-AI.git
   cd Predictive-Maintenance-AI
   ```
4. Double-click **`run_all.bat`**. It sets up Python, installs everything, trains the
   models, runs all tests, and opens the web app. The first run takes 10–15 minutes.
5. **Check it worked:**
   - `run_log.txt` ends with `58 passed` and `Tests passed.`
   - The browser shows the web app at http://localhost:8000.
   - The "Story" page says *60 machines, 95 six-hour shifts and 156 real failures*.

   If any of these differ, see [Troubleshooting](#13-rules-conventions-troubleshooting)
   before changing anything.
6. From now on, start the app with **`run_web.bat`**, or `run_streamlit.bat` for the
   older dashboard. Rerun `run_all.bat` only after changing the pipeline or config.

### Step 2: Understand the project (about 1 hour)

1. Read [§1 Headline results](#1-headline-results) and [§4 How the system works](#4-how-the-system-works).
2. Click through the web app using the [demo script (§7)](#7-demo-script-for-the-industry-review).
3. Read the code in this order: `config.py` → `src/fusion_engine.py` (top docstring) →
   `api/service.py` (top docstring) → `report/project_report.md`.
4. You should then be able to answer: *What does each ML model predict? Why do we
   calibrate? Why did calibration alone hurt compressors? What does S3 change?*
   [§8](#8-questions-to-expect-and-answers) has the answers.

### Step 3: Your tasks, in priority order

| # | Task | Where | Done when |
|---|---|---|---|
| 1 | **Write the research logbook**. This is a required deliverable. | `research/research_logbook.md` | All 10 entries in its table are written with real dates, each with: the problem, what was decided and the alternative rejected, the expected result, the actual result **with the file it comes from**, and what changed next. No number appears that isn't in `results/`. |
| 2 | **Rehearse the demo** on the presentation laptop and projector | web app | You can run the 12-minute script in §7 without notes; anything clipped or unreadable on the projector is fixed. |
| 3 | **Extended testing** | `tests/`, see [§11](#11-for-the-next-developer-testing-plan) | Each item in §11 has a test or a written result; `python -m pytest -q` passes; CI is green. |
| 4 | **Seed-robustness experiment** (enhancement #1) | new `src/robustness.py` | A table of mean ± std of the headline numbers over 5 seeds, added to the report and logbook. |
| 5 | **Cost view** and **editable consequence weights** (enhancements #2, #3) | `api/`, `frontend/src/pages/` | A user can enter ₹/hour per machine type and see the queue and expected cost change; inputs are clearly labelled as assumptions. |
| 6 | Other enhancements | [§12](#12-for-the-next-developer-enhancement-backlog) | As agreed with the team. |

### Step 4: How to work in this repo

```powershell
git checkout -b logbook               # one branch per task
# ...make changes...
python -m pytest -q                    # must pass before every commit
git add -A
git commit -m "Write logbook entries 1-3: problem, data, baseline models"
git push -u origin logbook             # then open a Pull Request on GitHub
```

- **CI runs on every push** (`.github/workflows/tests.yml`). Merge only when it is green.
- **Changed `config.py` or anything in `src/`?** Rerun `python main.py`, commit the
  updated `results/` folder, and update any numbers in this README and the report.
- **Changed the React frontend?** Run `cd frontend && npm install && npm run build` and
  commit `frontend/dist` too. The presentation laptop runs the built app and needs no
  Node.js.
- **Never commit** `.venv/`, `data/simulated/`, `data/processed/`, `models/*.pkl`,
  `frontend/node_modules/`, or `run_log.txt`. `.gitignore` already blocks them.
- **Don't change without discussing first:** the prediction-contract columns
  (`src/predict.py`), the test split, and the headline settings in `config.py`. They
  are what the report's numbers depend on.

### Step 5: Rules that keep the project defensible

- Never fit anything on the test set.
- Never write a number in the logbook, report or slides that the code didn't produce.
  Cite the CSV it comes from.
- Always say the data is simulated.

---

## Contents
0. [Teammate: start here](#-teammate-start-here)
1. [Headline results](#1-headline-results)
2. [Quick start](#2-quick-start)
3. [Project status and handoff](#3-project-status-and-handoff)
4. [How the system works](#4-how-the-system-works)
5. [Repository map](#5-repository-map)
6. [Results in detail](#6-results-in-detail)
7. [Demo script for the industry review](#7-demo-script-for-the-industry-review)
8. [Questions to expect, and answers](#8-questions-to-expect-and-answers)
9. [Path to deployment](#9-path-to-deployment)
10. [Limitations](#10-limitations)
11. [For the next developer: testing plan](#11-for-the-next-developer-testing-plan)
12. [For the next developer: enhancement backlog](#12-for-the-next-developer-enhancement-backlog)
13. [Rules, conventions, troubleshooting](#13-rules-conventions-troubleshooting)

---

## 1. Headline results

Test set: 60 machines, 95 six-hour review windows, crew capacity of 8 machines
per window. All numbers come from `python main.py` (seed 42) and are reproducible.

1. **Raw model scores are not comparable across machine types.** The compressor
   model predicts 21% average risk where the real rate is 8%. Per-class calibration
   cuts probability error (Brier score) by **24–53%**.
2. **Calibration alone is not safe.** On its own it pushes real compressor failures
   out of the queue: compressor recall falls **0.856 → 0.789** (95% CI of the change:
   −0.118 to −0.021, i.e. statistically significant). With a crew of 4, it falls
   **0.51 → 0.24**.
3. **Calibrated risk × severity × data freshness** (strategy S3) removes that loss.
   Overall recall is unchanged (0.828 vs 0.830 baseline). **S3 is the recommended
   default.** The class-coverage safeguard (S4) helps most when crew capacity is tight.

| Strategy | Recall@8 (95% CI) | Precision@8 | Worst-class recall | Compressor recall |
|---|---|---|---|---|
| S1 raw score | 0.830 (0.804–0.858) | 0.674 | 0.812 | 0.856 |
| S2 calibrated | 0.830 (0.802–0.858) | 0.674 | 0.789 | **0.789** ⚠ |
| **S3 calibrated × severity × freshness** | 0.828 (0.803–0.857) | 0.672 | 0.809 | 0.856 |
| S4 = S3 + class safeguard | 0.823 (0.796–0.852) | 0.668 | 0.804 | 0.856 |

### Where the machine learning is

| Step | ML or rule? | Where | Runs live in the web app? |
|---|---|---|---|
| Failure prediction: one model per machine type (Random Forest, Gradient Boosting, Logistic Regression), each giving P(failure within 24 h) from 19 sensor-trend inputs | **ML (supervised classification)** | `src/train_models.py`, `src/predict.py` | **Yes**: the *Why* panel and *What-if* simulator call the trained models on every request (`api/service.py`) |
| Calibration: re-scales each model's scores into real probabilities | **ML (isotonic regression)** | `src/fusion_engine.py` | **Yes**: applied to every live score |
| Sensor importance: which sensor each model relies on | ML analysis (grouped permutation importance) | `api/service.py` | Computed once at startup, then cached |
| Priority = calibrated risk × consequence × freshness, plus the class safeguard | **Rule**, kept transparent on purpose | `src/fusion_engine.py` | Yes, re-ranked live for any crew size and rule |

The API test `test_live_model_reproduces_pipeline_predictions` checks that the live
model in the web app gives exactly the same scores as the pipeline.

---

## 2. Quick start

### Windows (one click)
```bat
run_all.bat
```
This finds Python, creates `.venv`, installs requirements, runs the pipeline and the
tests, then starts the **web app** and opens http://localhost:8000. The full log goes to
`run_log.txt`; if anything fails, the window stays open and the log says why.

**After the first run**, don't rerun the pipeline every time. Instead use:
- `run_web.bat`: starts the web app (about 10–15 s)
- `run_streamlit.bat`: starts the original Streamlit dashboard

Keep the black command window open while presenting; closing it stops the app.

> Put the project **outside OneDrive** (e.g. `C:\Users\<you>\Documents\`). OneDrive
> tries to sync the Python environment and data files, which makes setup very slow.

### Step by step (Windows PowerShell, VS Code terminal)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: .venv\Scripts\activate.bat in cmd
pip install -r requirements.txt
python main.py                        # full pipeline, ~4–6 min on a laptop
python -m pytest -q                   # expect: 58 passed
python -m uvicorn api.main:app --port 8000   # web app -> http://localhost:8000
streamlit run dashboard/app.py               # Streamlit -> http://localhost:8501
```

### macOS / Linux
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py && python -m pytest -q && python -m uvicorn api.main:app --port 8000
```

### Running single stages
```bash
python main.py --stage simulate     # data/simulated/
python main.py --stage preprocess   # data/processed/
python main.py --stage train        # models/*.pkl
python main.py --stage predict      # results/predictions/predictions_{val,test}.csv
python main.py --stage evaluate     # model-level metrics + figures
python main.py --stage fusion       # calibration, 4 strategies, fairness, figures (~1 min)
python main.py --stage models       # simulate..evaluate (everything except fusion)
```

`data/` and `models/` are **not** in git (about 250 MB). `python main.py` regenerates
them identically. `results/` **is** in git, so the dashboard and report work right
after cloning, once `main.py` has run.

---

## 3. Project status and handoff

| Area | Status |
|---|---|
| Simulated 3-class, 60-machine plant with different data rates | ✅ Done |
| Feature engineering, leakage-safe chronological split | ✅ Done |
| One model per class + common prediction contract | ✅ Done |
| Model-level evaluation and fairness (per-class recall, miss rate, calibration) | ✅ Done |
| Alert manager (review windows, one snapshot per machine, new/ongoing) | ✅ Done |
| Fusion engine: calibration + 4 ranking strategies | ✅ Done |
| Fusion-level fairness: recall@k per class, buried alerts, bootstrap CIs, capacity sensitivity | ✅ Done |
| Web app: FastAPI backend with live model scoring + React frontend (6 pages) | ✅ Done |
| Streamlit dashboard (original, 5 tabs) | ✅ Kept as second frontend |
| Tests (58) + CI workflow | ✅ Done |
| Technical report with real numbers | ✅ `report/project_report.md` |
| **Research logbook** | ⏳ **Teammate** — template + evidence map in `research/research_logbook.md` |
| **Extended testing** | ⏳ **Teammate** — see [§11](#11-for-the-next-developer-testing-plan) |
| **Enhancements / new features** | ⏳ **Teammate** — see [§12](#12-for-the-next-developer-enhancement-backlog) |
| **Rehearse the demo on the presentation laptop and projector** | ⏳ **Teammate** — pages were checked at 1440 px and phone width; check on the actual screen |

**First 30 minutes for the next developer:**
1. Clone, run `run_all.bat` (or the steps above). Confirm `58 passed` in `run_log.txt`.
2. Open the web app and click through all 6 pages, using the demo script in [§7](#7-demo-script-for-the-industry-review).
3. Read, in order: §4 below → `config.py` → `src/fusion_engine.py` docstring → `report/project_report.md`.
4. Pick tasks from §11 and §12. Work on a branch; CI runs on every push.

---

## 4. How the system works

```
 Sensor streams          Features             Per-class models          Alert manager
 motor  every 15 min ─┐  2 h / 6 h      ┌─→ Motor: Random Forest ──┐   one snapshot per
 pump   every 30 min ─┼→ time windows ──┼─→ Pump:  Gradient Boost ─┼─→ machine per 6 h
 compr. every 60 min ─┘  + trend, gap   └─→ Compr: Logistic Reg. ──┘   window
                                                                          │
   Dashboard  ←  Top-k queue  ←  Class safeguard  ←  Priority = p̂ × severity × freshness
                     │           (S4, optional)                    ↑
                     ↓                                   Per-class calibration p̂
             Fairness evaluation                         (isotonic, fit on validation)
       recall@k per class, buried alerts,
       bootstrap CIs, capacity sensitivity
```

### 4.1 Data — `src/data_simulator.py`
Public PdM datasets each cover one machine type (NASA C-MAPSS = turbofans,
AI4I 2020 = one milling machine), so they cannot test *cross-class* fusion. The
simulator controls exactly the variables in the research question:

| Class | Machines | Sampling | Mean run-to-failure | Signal noise | Dropouts | Severity |
|---|---|---|---|---|---|---|
| Motor | 30 | 15 min | 8 days | 1.0× | 1% | 0.7 |
| Pump | 18 | 30 min | 10 days | 1.3× | 3% | 0.9 |
| Compressor | 12 | 60 min | 12 days | 1.8× (hardest) | 6% | 1.0 |

The simulation covers 120 days and 763 failures. Degradation follows `d = (t/T)³`,
so symptoms appear late in the cycle. Sensors combine a baseline, operating load,
degradation, noise and a per-machine offset. Each failure is followed by 4 h of
downtime. Random dropouts and outages create stale data.

**Target:** `failure_label = 1` if the machine fails within the next **24 h**.

### 4.2 Features and split — `src/data_preprocessing.py`
- Rolling mean/std over **2 h and 6 h of time** (not rows), plus a short-vs-long
  trend and the minutes since the last reading. A motor and a compressor therefore
  summarise the same physical duration despite different sampling rates.
- **Chronological** 60/20/20 split with a **24 h purge gap** before each cutoff. The
  label looks 24 h ahead, so without the gap, training labels would leak
  information from the validation period.

### 4.3 Models — `src/train_models.py`, `src/predict.py`
One model per class, with `class_weight="balanced"` because failures are rare. Three
different algorithms are used on purpose, mirroring a real plant where pilots are
built by different teams. Every model writes the same **prediction contract**
(`CONTRACT_COLUMNS` in `src/predict.py`). Downstream code depends only on that contract.

### 4.4 Alert manager — `src/alert_manager.py`
Every 6 h the maintenance lead sees **one row per machine** (its latest reading).
Counting raw readings, motors would produce 70% of alerts simply because they
report 4× more often. Windowing brings this down to 47%. The alert manager also
marks each queue entry as **new** or **ongoing**, and labels each snapshot with
ground truth: *fails within 24 h after the window ends*. That label is used for
evaluation only.

### 4.5 Fusion engine — `src/fusion_engine.py` (core R&D)
| ID | Priority score | What it tests |
|---|---|---|
| S1 | raw model score | baseline |
| S2 | calibrated risk p̂ | does making scores comparable help? |
| S3 | p̂ × severity × freshness | does adding consequence and data age help? |
| S4 | S3 + class-coverage safeguard | does guaranteed visibility help the weakest class? |

- **Calibration:** per-class isotonic regression, **fitted on validation only**.
  It is monotonic, so it never reorders machines within a class; it only fixes
  what the numbers mean.
- **Severity:** `config.SEVERITY_WEIGHTS`. These are *assumed* values (see §9).
- **Freshness:** `0.5 ** (age_min / 120)`. A 2-hour-old reading counts half.
- **Safeguard (S4):** a class with no machine in the top-k, but with one at
  calibrated risk ≥ 0.20, gets its best machine in. That machine replaces the
  lowest-ranked machine of the most-represented class, and is labelled "promoted".
- No separate "confidence" multiplier: calibration already expresses trust in
  the score, so multiplying again would double-count.

### 4.6 Evaluation — `src/evaluation.py`
- **Model level:** precision, recall, miss rate (FNR), F1, PR-AUC, Brier,
  calibration gap, event-level detection with lead time.
- **Fusion level:** recall@k overall and per class, precision@k, severity-weighted
  recall, worst-class recall, **buried alerts** (the machine's own model alerted
  and it really failed, but the queue left it out), queue share vs failure share,
  and windows where a class got zero slots.
- **Statistics:** paired bootstrap over review windows (1,000 resamples). Every
  strategy is compared with S1 on the same resampled windows. A CI that excludes 0
  indicates a real effect.
- **Capacity sensitivity:** all metrics for k = 2 … 16.

### 4.7 Web app: backend `api/`, frontend `frontend/`

**Backend (`api/service.py`, `api/main.py`, FastAPI).** It loads the trained models,
calibrators and pipeline outputs once at startup, about 10 s. It warms up the default
ranking and serves JSON:

| Endpoint | Returns | ML runs live? |
|---|---|---|
| `GET /api/fleet` | machines, classes, review windows, strategies | |
| `GET /api/window/{w}?strategy=&k=` | every machine's risk + the ranked queue for that shift, crew size `k` | re-ranks live |
| `GET /api/machine/{id}` | risk timeline, queue history, failures, hourly sensor history | |
| `GET /api/machine/{id}/explain/{w}` | per-sensor drivers: risk if that sensor were at its normal level | **yes** |
| `POST /api/machine/{id}/what-if` | `{window, deltas:{sensor: change}}` → new risk and new queue position | **yes** |
| `GET /api/story`, `/calibration`, `/fairness`, `/models` | headline numbers, reliability curves, fairness tables, model cards + sensor importance | |

Interactive API docs are at http://localhost:8000/docs.

*How "explain" works:* it rebuilds the machine's model inputs from raw readings, scores
them, then re-scores with one sensor's inputs replaced by that machine type's healthy
median. The drop in risk is that sensor's contribution. Contributions are not
additive; each one answers "what if only this sensor were normal?"

*How "what-if" works:* each slider shifts a sensor as if the change built up over the
last ~2 hours. Raw value and 2 h mean move fully, the 6 h mean moves half-way, and the
trend is recomputed. The real model re-scores, calibration is applied, and the whole
shift is re-ranked.

**Frontend (`frontend/`, React 18 + Vite + Apache ECharts).** The fonts are bundled, so it
works offline at the venue.

| Page | What it shows | Interactions |
|---|---|---|
| The story | Problem → trap → fix, each step with a live chart; live replay of the plant floor | crew-size sliders, raw/calibrated toggle |
| Control room | Plant floor map (60 machines in three bays, colour = risk, hazard stripes = in queue), ranked queue with plain reasons, "Why" panel | play/pause/speed replay, shift scrubber, ranking rule, crew size, reveal ground truth, click any machine |
| Machine detail | Risk timeline (raw vs calibrated, queue periods, failures), why panel, what-if simulator, linked sensor charts | click a point to inspect a shift, zoom, sensor sliders |
| Fairness lab | Recall vs crew size per machine type and rule, share of crew time vs share of failures, significance chart | rule toggles, machine-type switch, crew slider |
| The models | Model cards (recall, precision, PR-AUC, confusion), what each model listens to, calibration curves, data-rate effect | raw/calibrated toggle |
| How it works | Pipeline, priority rule, test protocol, ML vs rules, limits | |

Design rules: safety yellow means **only** "in the maintenance queue", signal red means
**only** "failure". Machine-type colours are fixed: motor blue, pump green, compressor
violet. Colours and wording live in `frontend/src/theme.js`.

**Changing the frontend** (needs Node.js 18+):
```bash
cd frontend
npm install            # once
npm run dev            # http://localhost:5173, hot reload; API calls go to :8000 (start uvicorn too)
npm run build          # writes frontend/dist; COMMIT dist so others can run without Node
```
`frontend/dist` is committed on purpose: the presentation laptop only needs Python.

### 4.8 Streamlit dashboard: `dashboard/app.py` (original frontend)
| Tab | Shows |
|---|---|
| 🚨 Alert queue | Top-k queue for any 6 h window, with explanation per row ("calibrated 0.42 × severity 1.0 × freshness 0.91"), new/ongoing status, and fleet risk map |
| 🔧 Machine detail | Raw vs calibrated risk over time, queue entries, actual failures, sensor history |
| ⚖️ Fairness & strategies | Key findings (computed live from CSVs), strategy table with CIs, per-class recall, capacity curves, queue share |
| 📈 Models | Per-class metrics, confusion matrices, PR curves, calibration before/after, data-rate effect |
| 📐 Method | Architecture, formula, evaluation protocol, limitations |

The sidebar has the strategy, the review window, and an **evaluation mode** toggle
that reveals ground truth (which machines really failed). It defaults to S3.

---

## 5. Repository map

```
predictive-maintenance/
├── config.py                  ALL settings (fleet, rates, horizon, split, severity, top-k, safeguard)
├── main.py                    pipeline entry point (stages)
├── run_all.bat                Windows one-click: setup + pipeline + tests + web app
├── run_web.bat                start the web app only (after the first run)
├── run_streamlit.bat          start the Streamlit dashboard only
├── requirements.txt
├── src/
│   ├── data_simulator.py      run-to-failure sensor simulation
│   ├── data_loader.py         loads data in the common schema (real data plugs in here)
│   ├── data_preprocessing.py  time-based features, chronological split + purge gap
│   ├── train_models.py        one model per class
│   ├── predict.py             prediction contract (CONTRACT_COLUMNS)
│   ├── alert_manager.py       review windows, snapshots, new/ongoing, alert volume
│   ├── fusion_engine.py       calibration, priority, S1–S4 ranking, experiment runner
│   └── evaluation.py          model-level + fusion-level metrics, bootstrap, figures
├── api/
│   ├── service.py             loads models; live explain / what-if / ranking; analysis data
│   └── main.py                FastAPI routes + serves the built React app
├── frontend/
│   ├── src/pages/             Story, ControlRoom, Machine, Fairness, Models, Method
│   ├── src/components/        FloorMap, Queue, WhyPanel, shared UI + chart wrapper
│   ├── src/theme.js           colours, names, chart styling
│   ├── dist/                  built app (committed; served by FastAPI)
│   └── package.json           React 18, Vite 5, ECharts 5
├── dashboard/app.py           Streamlit dashboard (original frontend)
├── tests/
│   ├── test_models.py         simulator, split/leakage, features, contract   (10)
│   ├── test_fusion.py         calibration, ranking, safeguard, windows, metrics, outputs (24)
│   ├── test_dashboard.py      Streamlit: headless render + every control     (3)
│   └── test_api.py            web API: live model = pipeline, queue, what-if, errors (21)
├── results/                   committed outputs (metrics CSVs, figures, ranked queues)
├── data/{simulated,processed,raw}/   regenerated, not committed
├── models/                    regenerated, not committed (*.pkl incl. calibrators)
├── research/research_logbook.md      template + evidence map (teammate)
├── report/project_report.md          technical report
└── .github/workflows/tests.yml       CI: pipeline + tests on every push
```

**Key output files**

| File | Content |
|---|---|
| `results/metrics/model_metrics.csv` | Per-class model metrics (val, test) |
| `results/metrics/calibration_report.csv` | Brier before/after calibration |
| `results/metrics/alert_volume_by_class.csv` | Data-rate effect |
| `results/metrics/strategy_comparison.csv` | S1–S4 with CIs and paired deltas vs S1 |
| `results/metrics/strategy_per_class.csv` | Per strategy × class: recall, buried, queue share, CIs |
| `results/metrics/k_sensitivity.csv` | All strategies across crew capacity k = 2…16 |
| `results/predictions/ranked_alerts_<S>.csv` | Full ranked queue per window per strategy |
| `results/figures/*.png` | Confusion matrices, PR curves, reliability, calibration, recall@k, queue share, k-sensitivity |

---

## 6. Results in detail

### Model level (test)
| Class | Model | Precision | Recall | Miss rate | PR-AUC | Mean predicted | Actual |
|---|---|---|---|---|---|---|---|
| Motor | Random Forest | 0.673 | 0.907 | 0.093 | 0.885 | 0.170 | 0.122 |
| Pump | Gradient Boosting | 0.596 | 0.957 | 0.043 | 0.900 | 0.182 | 0.110 |
| Compressor | Logistic Regression | 0.398 | 0.934 | 0.066 | 0.674 | 0.213 | 0.080 |

Recall is even across classes, so the models themselves do not miss any class.
Calibration is uneven, which means raw scores can't be ranked against each other.

### Calibration (test)
| Class | Brier raw | Brier calibrated | Improvement |
|---|---|---|---|
| Compressor | 0.088 | 0.041 | 53% |
| Pump | 0.053 | 0.029 | 45% |
| Motor | 0.046 | 0.035 | 24% |

### Compressor, by strategy (test, k = 8)
| Strategy | Recall@8 | Change vs S1 (95% CI) | Queue share | Failure share |
|---|---|---|---|---|
| S1 | 0.856 | — | 21% | 15% |
| S2 | 0.789 | **−0.067 (−0.118 to −0.021)** | 19% | 15% |
| S3 | 0.856 | 0.000 (−0.033 to +0.032) | 21% | 15% |
| S4 | 0.856 | 0.000 (−0.033 to +0.032) | 22% | 15% |

### Capacity sensitivity (recall by class; `k_sensitivity.csv`)
| k | Strategy | Overall | Motor | Pump | Compressor |
|---|---|---|---|---|---|
| 4 | S1 | 0.525 | 0.513 | 0.554 | 0.511 |
| 4 | S2 | 0.525 | 0.546 | 0.624 | **0.244** |
| 4 | S3 | 0.517 | **0.405** | 0.726 | 0.511 |
| 4 | S4 | 0.490 | 0.390 | 0.602 | **0.633** |
| 8 | S1 | 0.830 | 0.812 | 0.850 | 0.856 |
| 8 | S3 | 0.828 | 0.809 | 0.850 | 0.856 |

At default capacity (k = 8) the strategies differ only for compressors. At tight
capacity the choice matters a lot, and every option has a cost.

### Interpretation (say this in the review)
- **Why does calibration bury compressors?** The compressor model is the least
  separable (PR-AUC 0.67). After honest calibration, even its true failures receive
  only moderate probabilities, and sharper motor predictions outrank them. A
  probability-optimal ranking is not automatically consequence-optimal or fair.
- **S1 looks fair only by accident.** At tight capacity, raw scores give compressors
  good recall, but only because that model's over-confidence happens to favour them,
  at the price of many false alarms. A differently trained model would reverse this,
  so it is not a property to rely on.
- **Severity weighting is a policy choice, not a free lunch.** At tight capacity
  (k = 4), S3 deliberately moves slots from motors (lowest severity) to pumps and
  compressors: motor recall drops 0.51 → 0.41 while pump recall rises 0.55 → 0.73.
  That is the intended effect if a motor failure really costs less. The plant's
  downtime costs should decide the weights, not us.
- **Recommendation:** S3 by default. Turn on S4 when crew capacity is tight relative
  to alert volume (roughly k ≤ 6 here) and compressor visibility matters most.

---

## 7. Demo script for the industry review

About 12 minutes, in the **web app**. Start it with `run_web.bat` **before** the
meeting and open each page once, so everything is loaded. Never run the pipeline live.

| Min | Page | Do | Say |
|---|---|---|---|
| 0–2 | **The story**, hero | Let the floor map replay on its own | "Three machine types, three AI models, one crew. Which machine do you fix first?" |
| 2–4 | Story, step 1 | Toggle *Raw* → *After calibration* | "When the compressor model said 70–90%, compressors failed only about 25% of the time. The models don't speak the same language." |
| 4–5 | Story, steps 2–3 | Drag the crew slider down to 4 | "Fixing the language alone hides compressor failures. Weighting by consequence puts them back." |
| 5–8 | **Control room** | Press play at 2×, pause on a busy shift, tick *Reveal what actually happened* | "Every 6 hours the lead gets this queue. The models score each machine live. Here's what really failed, and the queue caught it." |
| 8–10 | Control room → click a queued machine → **Machine detail** | Show the *Why* panel, then drag a sensor slider in *What if* | "This is the AI working live: the real model re-scores the machine, and it moves in the queue." |
| 10–11 | **Fairness lab** | Switch to *Compressors*, toggle rules | "We measure fairness per machine type, with statistical confidence." |
| 11–12 | **How it works**, limits | | "Simulated data; next step is a pilot on one line's historian and maintenance records." |

If someone asks "where is the AI?", go to **How it works → Multi-machine modelling**,
then show the what-if slider.

---

## 8. Questions to expect, and answers

**Q: Is this on real plant data?**
No, it uses simulated data, and we say so up front. The simulator lets us control
data rates, failure rates and model quality, which is exactly what the research
question is about. The next step is a pilot on historian data from one line (§9).
The code reads data through one schema (`src/data_loader.py`), so real data plugs in
without changing the fusion logic.

**Q: Why not one big model for all machines?**
The machine types have different sensors (flow rate vs rpm) and different failure
physics. In practice, pilots also already exist per machine type, built by
different teams. The platform's job is to fuse what exists.

**Q: Where do the severity weights come from?**
They are assumptions in this prototype (compressor 1.0, pump 0.9, motor 0.7). In
deployment they should be replaced with downtime cost per hour or a criticality
ranking from plant engineering. They live in one config line. They have a real
effect when the crew is short: at k = 4, motor recall falls from 0.51 to 0.41 in
exchange for higher pump and compressor recall. That trade-off should reflect real
costs.

**Q: How much does this save?**
We don't claim a rupee figure from simulated data. What we can measure is that, at
the same crew capacity, the recommended strategy keeps 83% of real 24-hour
failures in the queue, with no machine type systematically left out. Translating
that into savings needs the plant's downtime cost per hour.

**Q: How do you know the differences are real and not noise?**
We use a paired bootstrap over 95 review windows. The compressor loss under
calibration-only has a 95% CI of −11.8 to −2.1 points, which excludes zero. Most
other differences are *not* significant, and we report them as such.

**Q: What if sensors go offline?**
The freshness factor halves a reading's weight every 2 hours. A machine with no
reading for 12 hours drops out of the queue (shown as not reporting), so it is
never ranked on stale evidence.

**Q: Won't the queue keep showing the same machine?**
Yes, if it stays high-risk. That's correct behaviour, and it is marked *ongoing*
rather than *new*, so the crew can see what has changed.

**Q: How is this different from a threshold alarm?**
A threshold says *whether* to alert. This system decides *which* alerts to act on
first when the crew can't do everything, and checks that the order is fair across
machine types.

**Q: What about model drift?**
It isn't handled yet. It's on the roadmap: monitor calibration (Brier per class)
weekly and refit calibrators on recent labelled data (§12).

---

## 9. Path to deployment

1. **Data:** connect the historian/SCADA (e.g. OPC-UA or an export from the plant
   historian) for one line. Map tags to `machine_id`, `machine_class` and sensor
   columns in `data_loader.py`. Get failure/work-order history from the CMMS for labels.
2. **Models:** retrain per class on plant data; keep the prediction contract.
3. **Severity:** replace `SEVERITY_WEIGHTS` with downtime cost per hour or a
   criticality matrix agreed with maintenance.
4. **Shadow mode (4–8 weeks):** the queue runs alongside current practice. Compare
   what it flagged against actual breakdowns and work orders.
5. **Go live:** export the queue to the CMMS as work requests. Monitor per-class
   calibration and recall@k monthly.

---

## 10. Limitations

- **Simulated data.** The results show how the fusion logic behaves under controlled
  conditions, not accuracy on real equipment.
- Severity weights are assumptions.
- Event-level recall saturates near 1.0, because simulated degradation is strong
  near failure. Reading-level and window-level metrics are the informative ones.
- A single model-alert threshold (0.5) is used, and model hyperparameters are not tuned.
- Calibrators are fitted once (no drift handling).

---

## 11. For the next developer: testing plan

**Existing tests (58, all passing).** Run them with `python -m pytest -q`; CI runs them on every push.

| File | Covers |
|---|---|
| `tests/test_models.py` | simulator schema per class, label = horizon rule, sampling rate, degradation signal present, chronological split + purge gap, time-based features, prediction contract |
| `tests/test_fusion.py` | freshness formula, priority formula, stale readings rank lower, calibrators refuse test data, calibration monotonic + bounded + improves Brier, S1/S2 order, determinism, S4 promotes eligible class / ignores ineligible / equals S3 when nothing to fix, one snapshot per machine per window, target & down-machine logic, new/ongoing, buried-alert counting, comparison shapes and CIs, real output files |
| `tests/test_dashboard.py` | Streamlit: all tabs render; queue size = TOP_K; every strategy, window, machine, radio; machine choice survives a window change |
| `tests/test_api.py` | web API: fleet/window shapes, queue size and order for every rule and crew size, live ranking = saved ranking, **live model = pipeline predictions**, what-if identity and direction, machine detail, all analysis endpoints JSON-safe, 404/422 errors |

**Testing tasks, in priority order:**
1. **Visual check** of every web-app page on the presentation laptop and a projector
   (pages were checked at 1440 px and 390 px). Fix anything clipped. Then add
   **Playwright end-to-end tests** for the web app (play the replay, reveal truth, move a
   what-if slider and check the gauge changes): `npm i -D @playwright/test`.
2. **Reproducibility test:** run the pipeline twice and assert identical
   `strategy_comparison.csv`.
3. **Leakage tests:** assert the calibrators' training rows all have `split == "val"`,
   and that no test timestamp falls before the validation end.
4. **Edge cases for `rank_window`:** fewer machines than k; all machines in one
   class; all risks equal; NaN risk (decide the behaviour: drop or raise).
5. **Edge cases for `build_windows`:** a machine silent for longer than 12 h; a
   failure exactly at a window end.
6. **Property tests** (`hypothesis`): S3 ranking is invariant to row order;
   priority stays in [0, 1].
7. **Robustness experiments:**
   - change `RANDOM_SEED` (e.g. 5 seeds) and report mean ± std of the headline numbers;
   - vary the severity weights ±20% and check the S3 conclusion still holds;
   - try `REVIEW_WINDOW_HOURS` 4 / 8 / 12.
8. **Performance:** time each stage; keep the full run under 10 min on a laptop.

---

## 12. For the next developer: enhancement backlog

Ordered by value for the review. "Where" names the file to change.

| # | Enhancement | Where | Notes |
|---|---|---|---|
| 1 | **Seed-robustness table** (5 seeds, mean ± std) | new `src/robustness.py`, add a stage in `main.py` | Strongest answer to "is this a fluke?" |
| 2 | **Cost view:** expected downtime cost avoided per strategy, with editable ₹/hour inputs per class | new `/api/cost` endpoint + a page in `frontend/src/pages/` | Speaks the industrialist's language. Label the inputs as assumptions |
| 3 | **Editable consequence weights in the UI**, re-ranking live | `api/service.py` (accept weights), Control room | Lets the client plug in their own downtime costs |
| 4 | **Drift monitoring:** rolling per-class Brier, with a recalibration trigger | `fusion_engine.py`, new web page | |
| 5 | **Power BI version** of the dashboard on the CSVs in `results/` | `dashboard/powerbi/` | The brief mentions Grafana/Power BI |
| 6 | **Learned fusion weights** (e.g. tune severity to maximise worst-class recall on validation) | `fusion_engine.py`, new strategy S5 | Must be evaluated on test only once |
| 7 | **Real dataset plug-in** (e.g. AI4I 2020 as a 4th class) | `data_loader.py`, `config.MACHINE_CLASSES` | Shows the schema works on real data |
| 8 | **Remaining-useful-life view** using `time_to_failure_h` | new model per class | |
| 9 | **CMMS export:** queue as work-request CSV | `alert_manager.py` | |
| 10 | Hyperparameter tuning per class (on validation) | `train_models.py` | Re-run everything after |

**Adding a strategy:** add the score column in `fusion_engine.add_priority_components`,
an entry in `config.STRATEGIES`, a colour in `STRATEGY_COLORS` (`evaluation.py` and
`dashboard/app.py`), an entry in `STRATEGY` in `frontend/src/theme.js`, and an `_explain`
branch. Rebuild the frontend (`npm run build`). Everything else (comparison, CIs,
figures, both frontends) picks it up automatically.

**Adding a machine class:** add it to `config.MACHINE_CLASSES` (plus `SEVERITY_WEIGHTS`,
`MODEL_CHOICE`), give it a sensor model in `data_simulator._sensor_values`, a prefix
in `simulate_all`, and a colour in `CLASS_COLORS`. Then re-run `python main.py`.

---

## 13. Rules, conventions, troubleshooting

**Rules (don't break these, or the results stop being defensible):**
- **Never fit anything on the test set.** Models fit on train; calibrators fit on
  validation; test is for final numbers only.
- **Never write a number in the report, logbook or slides that the code didn't
  produce.** Cite the CSV.
- **Don't rename prediction-contract columns** (`src/predict.py`) without updating
  all downstream code. The tests will catch it.
- All tunables go in `config.py`. After changing config, run `python main.py`
  (full), then `pytest`.
- `results/` is committed. Re-run and commit it whenever code or config changes, so
  the repo stays consistent. Re-running with unchanged code gives identical CSVs; PNG
  figures may differ at pixel level across library versions (the CSVs are the
  source of truth).

**Git workflow:** branch per task → push → CI must be green → merge. Commit messages
should say what changed and why.

**Troubleshooting**

| Problem | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | Use cmd: `.venv\Scripts\activate.bat`, or run `run_all.bat` |
| Dashboard says "Missing results/…" | Run `python main.py` from the project root |
| Web app shows "can't reach the plant data" | Start the server (`run_web.bat`); if it still fails, the server window shows which file is missing; run `run_all.bat` |
| Browser opened before the server was ready | Refresh after a few seconds; the server loads models for ~10 s at startup |
| Web app shows "Frontend not built" | `cd frontend && npm install && npm run build` (needs Node.js) |
| Port 8000 or 8501 already in use | Close the other app window, or run `python -m uvicorn api.main:app --port 8010` |
| `run_all.bat` window closes instantly / "Python was not found" | Install Python 3.10+ from python.org with "Add python.exe to PATH" ticked; see `run_log.txt` |
| First setup very slow | Project is inside OneDrive; move it to a normal folder |
| Machine-detail sensor chart says "needs data/simulated" | Run `python main.py` (data isn't in git) |
| `ModuleNotFoundError: src` / `config` | Run commands from the project root, not from `src/` |
| Tests skipped | Output-dependent tests skip until `python main.py` has run |
| Numbers differ from this README | Something in `config.py` changed. Re-run and update the docs from the CSVs |
| Pipeline slow | `train` is the slowest stage (Random Forest on ~200k rows); reduce `n_estimators` in `train_models.py` while developing |
